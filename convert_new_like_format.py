import json
from pathlib import Path

from time_util import convert_datetime_format


def tfmt(str):
    try:
        return convert_datetime_format(str, target_tz="UTC")
    except Exception:
        return str


def map_sub(t, backup_time=None):
    if not t or not isinstance(t, dict):
        return None
    author = t.get("author") or {}
    new_author = {
        "user_id": author.get("id"),
        "user_nick": author.get("nickname"),
        "user_name": author.get("username"),
    }
    if author.get("avatar_url"):
        new_author["avatar"] = {"media_url": author.get("avatar_url")}
    if t.get("tombstone") is not None:
        out = {
            "tweet_id": t["rest_id"],
            **new_author,
            "tombstone": t.get("tombstone"),
        }
    else:
        out = {
            "tweet_id": t.get("rest_id"),
            **new_author,
            "tweet_content": t.get("content"),
            "tweet_created_at": tfmt(t.get("created_at")),
            "quoted_tweet": map_sub(t.get("quoted_tweet")),
            "retweeted_tweet": map_sub(t.get("retweeted_tweet")),
            "view_count": t.get("view_count"),
            "favorite_count": t.get("favorite_count"),
            "reply_count": t.get("reply_count"),
            "retweet_count": t.get("retweet_count"),
            "quote_count": t.get("quote_count"),
            "in_reply_to_status_id": t.get("in_reply_to_status_id"),
            "in_reply_to_screen_name": t.get("in_reply_to_screen_name"),
        }
        if media := t.get("media"):
            out["tweet_media"] = media
        
        if backup_time:
            out["updated_at"] = tfmt(out.get("updated_at") or backup_time)

    return out


def convert(
    src=Path("new_like_format.json"),
    dst=Path("sites/liked_tweets/liked_tweets_merged.from_new.json"),
):
    raw = json.loads(src.read_text(encoding="utf-8"))
    backup_time = raw.get("backup_time")
    tweets = [
        x
        for x in (map_sub(entry, backup_time) for entry in (raw.get("data") or []))
        if x and x.get("tweet_id")
    ]
    out = {"tweet_count": len(tweets), "tweets": tweets}
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return dst


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(
        description="Convert new_like_format.json -> liked_tweets_merged.json schema"
    )
    p.add_argument("--in", dest="src", default="new_like_format.json")
    p.add_argument(
        "--out",
        dest="dst",
        default="sites/liked_tweets/liked_tweets_merged.from_new.json",
    )
    a = p.parse_args()
    print(f"Converted -> {convert(Path(a.src), Path(a.dst)).resolve()}")
