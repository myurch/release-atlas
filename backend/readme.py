"""Bounded, unauthenticated public GitHub README fetching. No arbitrary URL proxy."""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import re
from urllib.parse import quote, urlsplit

import httpx
from pydantic import Field

from .input_validation import json_object
from .models import SourceInput, Strict

TIMEOUT = 20
RESPONSE_LIMIT = 250_000
SHA = re.compile(r'^[a-f0-9]{40}(?:[a-f0-9]{24})?$')


class ReadmeError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


class ReadmeDraft(Strict):
    source: SourceInput
    repository: str = Field(max_length=160)
    commit: str = Field(pattern=r'^[a-f0-9]{40}(?:[a-f0-9]{24})?$')
    path: str = Field(min_length=1, max_length=500)


def repository_from_url(url: str):
    message = 'Enter a public GitHub repository URL such as https://github.com/owner/repository. Other websites and file URLs are not supported.'
    try:
        parts = urlsplit(url.strip())
        if (parts.scheme != 'https' or parts.netloc.lower() != 'github.com' or parts.query or parts.fragment
                or parts.username or parts.password or any(char.isspace() for char in url)):
            raise ValueError('Unsupported URL')
        path = parts.path.removesuffix('/').removeprefix('/')
        path = path.removesuffix('.git')
        if len(path) > 160 or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}/[A-Za-z0-9_.-]{1,100}', path):
            raise ValueError('Unsupported repository')
        if any(part in ('.','..') for part in path.split('/')):
            raise ValueError('Invalid repository')
        return path
    except ValueError as exc:
        raise ReadmeError(422, message) from exc


async def github_json(client, path, *, params=None, missing='repository'):
    async with client.stream('GET','https://api.github.com'+path,params=params) as response:
        status = response.status_code
        if status == 404:
            if missing == 'readme':
                raise ReadmeError(404,'This public repository has no README available at the fetched commit. Paste source text manually or choose another repository.')
            if missing == 'commit':
                raise ReadmeError(404,'This public repository has no readable default-branch commit or README. Paste source text manually.')
            raise ReadmeError(404,'Public repository not found. Check the URL; private repositories are not supported.')
        if status in (403,429):
            raise ReadmeError(503,'GitHub denied the request or its public API rate limit was reached. Wait and try again, or paste the README manually.')
        if status == 409 and missing == 'commit':
            raise ReadmeError(404,'This public repository has no committed README yet. Paste source text manually or choose another repository.')
        if 300 <= status < 400:
            raise ReadmeError(422,'GitHub redirected this repository. Open GitHub and use its current repository URL; Atlas does not follow redirects.')
        if status >= 500:
            raise ReadmeError(502,'GitHub is temporarily unavailable. Try Fetch README again later. Your draft is unchanged.')
        if status != 200:
            raise ReadmeError(502,'GitHub could not return this README. Check the repository URL or paste the text manually.')
        data = bytearray()
        async for chunk in response.aiter_bytes():
            data.extend(chunk)
            if len(data) > RESPONSE_LIMIT:
                raise ReadmeError(422,'GitHub returned more data than Atlas can safely fetch. Paste a smaller README excerpt manually; nothing was truncated or saved.')
    return json_object(data)


async def fetch_readme(url: str, transport=None):
    repository = repository_from_url(url)
    try:
        async with asyncio.timeout(TIMEOUT):
            # No caller/provider credentials, environment proxies, cookies or redirects.
            async with httpx.AsyncClient(timeout=10,trust_env=False,follow_redirects=False,transport=transport,
                    headers={'Accept':'application/vnd.github+json','User-Agent':'Release-Atlas/0.1',
                             'X-GitHub-Api-Version':'2022-11-28'}) as client:
                root = '/repos/'+repository
                info = await github_json(client,root)
                if info.get('private') is not False or info.get('visibility') not in (None,'public'):
                    raise ReadmeError(422,'Only public GitHub repositories are supported.')
                branch = info.get('default_branch')
                if not isinstance(branch,str) or not 1 <= len(branch) <= 200:
                    raise ReadmeError(404,'This public repository has no readable default branch or README. Paste source text manually.')
                commit_info = await github_json(client,root+'/commits/'+quote(branch,safe=''),missing='commit')
                commit = commit_info.get('sha')
                if not isinstance(commit,str) or not SHA.fullmatch(commit):
                    raise ValueError('Invalid commit')
                document = await github_json(client,root+'/readme',params={'ref':commit},missing='readme')
        if document.get('type') != 'file' or document.get('encoding') != 'base64':
            raise ValueError('Expected encoded README file')
        path = document.get('path')
        content = document.get('content')
        size = document.get('size')
        if (not isinstance(path,str) or not 1 <= len(path) <= 500 or '\\' in path
                or any(part in ('','.','..') for part in path.split('/'))
                or not re.fullmatch(r'README(?:\.[A-Za-z0-9_-]+)?',path.split('/')[-1],re.I)
                or not isinstance(content,str) or type(size) is not int or size < 0):
            raise ValueError('Invalid README metadata')
        raw = base64.b64decode(re.sub(r'\s','',content),validate=True)
        if len(raw) != size:
            raise ValueError('README size mismatch')
        blob_sha = document.get('sha')
        if not isinstance(blob_sha,str) or not SHA.fullmatch(blob_sha):
            raise ValueError('Invalid README blob hash')
        blob = b'blob '+str(len(raw)).encode()+b'\0'+raw
        actual_sha = (hashlib.sha1(blob) if len(blob_sha) == 40 else hashlib.sha256(blob)).hexdigest()
        if actual_sha != blob_sha:
            raise ValueError('README blob hash mismatch')
        text = raw.decode('utf-8')
        if not text.strip():
            raise ReadmeError(422,'This repository has an empty README. Paste source text manually or choose another repository.')
        if len(text) > 12000:
            raise ReadmeError(422,'This README exceeds the 12,000-character source limit. Paste a smaller excerpt manually; nothing was truncated or saved.')
        source = SourceInput(title=(repository+' README')[:160],version='commit:'+commit,text=text,
            url='https://github.com/'+repository+'/blob/'+commit+'/'+quote(path,safe='/'))
        return ReadmeDraft(source=source,repository=repository,commit=commit,path=path)
    except ReadmeError:
        raise
    except (httpx.TimeoutException,TimeoutError) as exc:
        raise ReadmeError(504,'GitHub did not respond in time. Try Fetch README again or paste the README manually. Your draft is unchanged.') from exc
    except httpx.HTTPError as exc:
        raise ReadmeError(502,'Could not connect to GitHub. Check the server internet connection and try Fetch README again. Your draft is unchanged.') from exc
    except (ValueError,TypeError,binascii.Error) as exc:
        raise ReadmeError(502,'GitHub returned unreadable or invalid README data. Paste the README manually or try again later. Your draft is unchanged.') from exc
