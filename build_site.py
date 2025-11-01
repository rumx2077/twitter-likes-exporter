import json
import math
from pathlib import Path
from shutil import copy2
import shutil

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import config
from time_util import convert_datetime_format


def build_site():
    ROOT_DIR = Path(__file__).resolve().parent

    # tweets_dir = config["site_path"] / "tweets"
    # tweets_dir.mkdir(exist_ok=True)

    theme_dir = Path(
        config.get("theme_dir", "{root_dir}/site_theme").format(root_dir=str(ROOT_DIR))
    )
    if not theme_dir.exists():
        raise FileNotFoundError(f"Theme directory not found: {theme_dir}")

    static_dir = theme_dir / "static"
    if static_dir.exists():
        shutil.copytree(static_dir, config["site_path"] / "static", dirs_exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(theme_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    input_json_path = config["merged_json_path"]
    if not input_json_path.exists():
        raise FileNotFoundError(f"Input JSON not found: {input_json_path}")

    tweets_data = json.loads(input_json_path.read_text(encoding="utf-8"))
    if isinstance(tweets_data, dict) and "tweets" in tweets_data:
        tweets = tweets_data["tweets"]
    else:
        tweets = tweets_data

    tweets = [_adjust_times(t) for t in tweets]

    tpl = env.get_template("tweets.html")

    items_per_page = config.get("items_per_page") or len(tweets)

    total_pages = max(1, math.ceil(len(tweets) / items_per_page))

    site_path = config["site_path"]
    html_files = [p for p in site_path.glob("*.html")]
    backups, generated_paths, success = [], [], False
    try:
        for f in html_files:
            b = f.with_name(f"{f.stem}.old{f.suffix}")
            f.replace(b)
            backups.append((f, b))

        for page in range(1, total_pages + 1):
            start = (page - 1) * items_per_page
            end = start + items_per_page
            page_tweets = tweets[start:end]
            context = {
                "title": "Liked Tweets Export",
                "base_path": "",
                "tweets": page_tweets,
            }
            if total_pages > 1:
                prev_url = _page_filename(page - 1) if page > 1 else None
                next_url = _page_filename(page + 1) if page < total_pages else None
                page_links = [
                    {"num": p, "url": _page_filename(p)}
                    for p in range(1, total_pages + 1)
                ]
                context |= {
                    "page_num": page,
                    "total_pages": total_pages,
                    "prev_url": prev_url,
                    "next_url": next_url,
                    "page_links": page_links,
                }
            out_path = site_path / _page_filename(page)
            out_path.write_text(tpl.render(**context), encoding="utf-8")
            generated_paths.append(out_path)

        if len(generated_paths) != total_pages:
            raise RuntimeError("incomplete generation")
        success = True
    finally:
        if success:
            for _, b in backups:
                b.unlink(missing_ok=True)

    index_path = config["site_path"] / config["index_page_filename"]
    print(f"喜欢页面已生成，共 {total_pages} 页；首页：{index_path.resolve()}")


def _page_filename(page_number: int) -> str:
    # Page 1 uses the configured index filename; others use index_page_filename-page-{n}.html
    return (
        config["index_page_filename"]
        if page_number == 1
        else f"{config["index_page_filename"]}-page-{page_number}.html"
    )


def _adjust_times(tweet):
    quote = tweet.get("quoted_tweet") or tweet.get("retweeted_tweet")
    for t in [tweet, quote]:
        for time_key in ("tweet_created_at", "updated_at", "tombstone_updated_at"):
            if t and time_key in t:
                t[time_key] = convert_datetime_format(
                    t[time_key],
                    target_tz=config["timezone"],
                )
    return tweet


if __name__ == "__main__":
    build_site()
