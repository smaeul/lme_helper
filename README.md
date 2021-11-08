# Linux mainlining effort helper

This tool parses the wikitext for the large status matrix table on the
[linux-sunxi wiki]'s [Linux mainlining effort] page.

[linux-sunxi wiki]: https://linux-sunxi.org
[Linux mainlining effort]: https://linux-sunxi.org/Linux_mainlining_effort

## Dependencies

This tool depends on `peewee` and `wikitextparser`.

## Usage

```sh
curl https://linux-sunxi.org/Special:Export/Linux_mainlining_effort > lme.xml
python3 lme_helper.py import lme.xml lme.db
sqlite3 lme.db # make changes
python3 lme_helper.py export lme.db lme_updated.wiki
```

Then copy and paste the contents of `lme_updated.wiki` into the MediaWiki
editor.
