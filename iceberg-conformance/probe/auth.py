# -*- coding: utf-8 -*-
"""Auth providers for Iceberg REST catalog endpoints.

Every provider exposes the same call:

    apply(method, url, headers, body) -> headers

so the runner never needs to know how a given vendor authenticates. SigV4 has
to see the method, URL and body to compute a signature, which is why the
interface passes all four rather than just returning a static header.
"""
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request


class AuthError(RuntimeError):
    pass


def _sh(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise AuthError("%s failed: %s" % (" ".join(cmd), p.stderr.strip()[:300]))
    return p.stdout.strip()


class Auth(object):
    kind = "none"

    def apply(self, method, url, headers, body):
        return headers


class NoAuth(Auth):
    pass


class BearerEnv(Auth):
    """Static bearer token read from an environment variable."""
    kind = "bearer_env"

    def __init__(self, env_var, **_):
        self.env_var = env_var

    def apply(self, method, url, headers, body):
        tok = os.environ.get(self.env_var)
        if not tok:
            raise AuthError("env var %s is unset" % self.env_var)
        h = dict(headers)
        h["Authorization"] = "Bearer " + tok
        return h


class _CachedToken(Auth):
    """Base for providers that mint a token with a TTL."""

    def __init__(self):
        self._tok = None
        self._exp = 0.0

    def _mint(self):
        raise NotImplementedError

    def token(self):
        if self._tok and time.time() < self._exp - 60:
            return self._tok
        self._tok, ttl = self._mint()
        self._exp = time.time() + ttl
        return self._tok

    def apply(self, method, url, headers, body):
        h = dict(headers)
        h["Authorization"] = "Bearer " + self.token()
        return h


class GcloudADC(_CachedToken):
    """Google Cloud: shells out to gcloud for an access token."""
    kind = "gcloud"

    def __init__(self, **_):
        _CachedToken.__init__(self)

    def _mint(self):
        return _sh(["gcloud", "auth", "print-access-token"]), 3000.0


class AzureCLI(_CachedToken):
    """Microsoft OneLake: token for the storage resource via the az CLI."""
    kind = "azure_cli"

    def __init__(self, resource="https://storage.azure.com", **_):
        _CachedToken.__init__(self)
        self.resource = resource

    def _mint(self):
        out = _sh(["az", "account", "get-access-token",
                   "--resource", self.resource, "-o", "json"])
        return json.loads(out)["accessToken"], 3000.0


class OAuth2ClientCredentials(_CachedToken):
    """The IRC-standard OAuth2 client_credentials flow (Polaris, Unity, Snowflake).

    Client id/secret come from env vars so secrets never land in the config file.
    """
    kind = "oauth2"

    def __init__(self, token_url, client_id_env, client_secret_env, scope=None, **_):
        _CachedToken.__init__(self)
        self.token_url = token_url
        self.cid_env = client_id_env
        self.csec_env = client_secret_env
        self.scope = scope

    def _mint(self):
        cid = os.environ.get(self.cid_env)
        sec = os.environ.get(self.csec_env)
        if not cid or not sec:
            raise AuthError("env vars %s / %s must both be set" % (self.cid_env, self.csec_env))
        form = {"grant_type": "client_credentials", "client_id": cid, "client_secret": sec}
        if self.scope:
            form["scope"] = self.scope
        data = urllib.parse.urlencode(form).encode()
        req = urllib.request.Request(
            self.token_url, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode())
        if "access_token" not in payload:
            raise AuthError("token endpoint returned no access_token: %s" % str(payload)[:200])
        return payload["access_token"], float(payload.get("expires_in", 3600))


class SnowflakeKeyPair(_CachedToken):
    """Snowflake Horizon: key-pair JWT exchanged for a catalog access token.

    Snowflake's flow differs from stock Polaris in two ways worth noting, since
    Horizon embeds Polaris: the scope is `session:role:<role>` rather than
    `PRINCIPAL_ROLE:ALL`, and the client_credentials grant carries a signed JWT
    in `client_secret` with no client_id at all. So this cannot reuse the
    generic oauth2 provider.

    Key-pair auth is used deliberately: no account password is ever handled.
    """
    kind = "snowflake_keypair"

    def __init__(self, account, user, private_key_file, role,
                 token_url=None, host=None, **_):
        _CachedToken.__init__(self)
        self.account = account.upper()
        self.user = user.upper()
        self.key_file = private_key_file
        self.role = role
        self.token_url = token_url or (
            host.rstrip("/") + "/polaris/api/catalog/v1/oauth/tokens")

    def _jwt(self):
        import base64
        import datetime as dt
        import hashlib
        import jwt as pyjwt
        from cryptography.hazmat.primitives import serialization
        with open(self.key_file, "rb") as f:
            priv = serialization.load_pem_private_key(f.read(), password=None)
        der = priv.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo)
        fp = "SHA256:" + base64.b64encode(hashlib.sha256(der).digest()).decode()
        now = dt.datetime.now(dt.timezone.utc)
        return pyjwt.encode({"iss": "%s.%s.%s" % (self.account, self.user, fp),
                             "sub": "%s.%s" % (self.account, self.user),
                             "iat": now,
                             "exp": now + dt.timedelta(minutes=55)},
                            priv, algorithm="RS256")

    def _mint(self):
        data = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "scope": "session:role:%s" % self.role,
            "client_secret": self._jwt(),
        }).encode()
        req = urllib.request.Request(
            self.token_url, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode())
        if "access_token" not in payload:
            raise AuthError("no access_token from Snowflake: %s" % str(payload)[:200])
        return payload["access_token"], float(payload.get("expires_in", 3600))


class SigV4(Auth):
    """AWS Glue and S3 Tables. Signs the real request, so it needs the body."""
    kind = "sigv4"

    def __init__(self, service, region, **_):
        self.service = service
        self.region = region
        self._creds = None

    def _credentials(self):
        if self._creds is None:
            from botocore.session import Session
            c = Session().get_credentials()
            if c is None:
                raise AuthError("no AWS credentials found (configure the aws CLI or set env vars)")
            self._creds = c.get_frozen_credentials()
        return self._creds

    def apply(self, method, url, headers, body):
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest
        h = dict(headers)
        h.pop("Authorization", None)
        req = AWSRequest(method=method, url=url, data=body or b"", headers=h)
        SigV4Auth(self._credentials(), self.service, self.region).add_auth(req)
        return dict(req.headers)


_PROVIDERS = {
    "none": NoAuth,
    "bearer_env": BearerEnv,
    "gcloud": GcloudADC,
    "azure_cli": AzureCLI,
    "oauth2": OAuth2ClientCredentials,
    "sigv4": SigV4,
    "snowflake_keypair": SnowflakeKeyPair,
}


def build(spec):
    """spec is the `auth:` mapping from catalogs.yaml; `type` selects the provider."""
    if not spec:
        return NoAuth()
    cfg = dict(spec)
    kind = cfg.pop("type", "none")
    if kind not in _PROVIDERS:
        raise AuthError("unknown auth type %r (have: %s)" % (kind, ", ".join(sorted(_PROVIDERS))))
    return _PROVIDERS[kind](**cfg)
