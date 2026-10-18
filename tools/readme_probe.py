"""Opt-in public GitHub README check. No source text, credentials or workspace writes."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from backend.readme import ReadmeError, fetch_readme


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--url',default='https://github.com/octocat/Hello-World')
    args = parser.parse_args()
    if not args.live:
        parser.error('--live is required for public network requests')
    report = {'saved_source_text':False,'workspace_modified':False,'browser_tested':False}
    try:
        preview = await fetch_readme(args.url)
        report.update(result='PASS',repository=preview.repository,commit=preview.commit,path=preview.path,
                      origin=preview.source.url,characters=len(preview.source.text),
                      sha256=hashlib.sha256(preview.source.text.encode()).hexdigest())
    except ReadmeError as error:
        report.update(result='UNVERIFIED',status=error.status,message=str(error))
    (ROOT/'validation/readme-integration-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return 0 if report['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
