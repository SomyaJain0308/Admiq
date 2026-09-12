"""
Drop-in replacement for fastapi_limiter.depends.RateLimiter.

fastapi-limiter==0.1.6 (pinned in requirements.txt) walks request.app.routes
and assumes every entry has .path and .methods (true for plain Route
objects). Newer FastAPI versions also put router-inclusion wrapper objects
(e.g. _IncludedRouter) in that same list, which have neither attribute, so
the upstream RateLimiter.__call__ raises AttributeError on the very first
request to any endpoint that depends on it - before it ever gets to
checking Redis.

This subclass only overrides __call__ to skip entries missing those
attributes when computing the route/dependency index used in the rate-limit
key; the counting logic itself (Redis eval, callback) is untouched, copied
verbatim from upstream. Remove this once fastapi-limiter ships a fix for
this and the pin in requirements.txt is bumped past it.
"""

import redis as pyredis
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter as _UpstreamRateLimiter
from starlette.requests import Request
from starlette.responses import Response

from backend.app.monitoring.api_metrics import RATE_LIMIT_REJECTIONS


class RateLimiter(_UpstreamRateLimiter):
    async def __call__(self, request: Request, response: Response):
        if not FastAPILimiter.redis:
            raise Exception("You must call FastAPILimiter.init in startup event of fastapi!")

        route_index = 0
        dep_index = 0
        for i, route in enumerate(request.app.routes):
            if getattr(route, "path", None) != request.scope["path"]:
                continue
            if request.method not in getattr(route, "methods", ()):
                continue
            route_index = i
            for j, dependency in enumerate(getattr(route, "dependencies", ())):
                if self is dependency.dependency:
                    dep_index = j
                    break
            break

        identifier = self.identifier or FastAPILimiter.identifier
        callback = self.callback or FastAPILimiter.http_callback
        rate_key = await identifier(request)
        key = f"{FastAPILimiter.prefix}:{rate_key}:{route_index}:{dep_index}"
        try:
            pexpire = await self._check(key)
        except pyredis.exceptions.NoScriptError:
            FastAPILimiter.lua_sha = await FastAPILimiter.redis.script_load(FastAPILimiter.lua_script)
            pexpire = await self._check(key)
        if pexpire != 0:
            RATE_LIMIT_REJECTIONS.labels(route=request.scope["path"]).inc()
            return await callback(request, response, pexpire)
