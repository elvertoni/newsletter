#!/usr/bin/env python3
"""
Hermes Newsletter — Coleta de tweets via X GraphQL API (guest access).

Usa httpx com User-Agent de browser + guest token para acessar a API GraphQL
do X sem necessidade de login, developer account ou credenciais.

Zero dependência de twscrape — funciona direto do IP da VPS.

Uso:
    python collect.py                          # salva em tweets.json
    python collect.py --output /tmp/t.json     # output customizado
    python collect.py --dry-run                # só imprime, não salva
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

# ── Config ───────────────────────────────────────────────────────────
PROFILES = [
    "songjunkr", "OpenAI", "ClaudeDevs", "huggingface",
    "NanoClaw_AI", "opencode", "shiri_shh", "brivael",
    "alibaba_cloud", "wangray", "openclaw", "Hostinger",
    "elonmusk", "cryptopunk7213", "theo", "AkitaOnRails",
    "BytePlusGlobal", "gmi_cloud", "nahcrof", "warpdotdev",
    "Lonely__MH", "odysseyml", "vllm_project", "karpathy",
    "Abmankendrick", "baseten", "Kimi_Moonshot", "ctatedev",
    "joshua_xu_", "cavalry__app", "QuiverAI", "HeyGen",
    "ollama", "Alibaba_Qwen", "makulas1913", "birdabo",
    "berryxia", "leftcurvedev_",
]

OUTPUT_DIR = Path(os.environ.get("HERMES_NEWSLETTER_DIR", Path.home() / ".hermes/cron/output"))
OUTPUT_FILE = OUTPUT_DIR / "tweets.json"
MAX_TWEETS_PER_USER = 10

# X GraphQL endpoint IDs (from twscrape source)
GQL_URL = "https://x.com/i/api/graphql"
OP_USER_BY_SCREEN_NAME = "32pL5BWe9WKeSK1MoPvFQQ/UserByScreenName"
OP_USER_TWEETS = "HeWHY26ItCfUmm1e6ITjeA/UserTweets"

# Bearer token (public, from X web client)
BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# Features payload for GraphQL requests
FEATURES = json.dumps({
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
})

# Browser-like User-Agent
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 24h cutoff in UTC
CUTOFF = datetime.now(timezone.utc) - timedelta(hours=24)

# ── HTTP Session ─────────────────────────────────────────────────────

class XClient:
    """Minimal X GraphQL client with guest token handling."""

    def __init__(self):
        self.client = httpx.Client(
            headers={
                "User-Agent": UA,
                "Authorization": f"Bearer {BEARER_TOKEN}",
            },
            timeout=30,
        )
        self._guest_token = None

    def _ensure_guest_token(self):
        if self._guest_token:
            return
        resp = self.client.post("https://api.x.com/1.1/guest/activate.json")
        if resp.status_code == 200:
            self._guest_token = resp.json().get("guest_token", "")
            self.client.headers["X-Guest-Token"] = self._guest_token

    def _gql(self, op: str, variables: dict) -> dict | None:
        """Make a GraphQL request. Returns parsed JSON or None on failure."""
        self._ensure_guest_token()
        params = {
            "variables": json.dumps(variables),
            "features": FEATURES,
        }
        try:
            resp = self.client.get(f"{GQL_URL}/{op}", params=params)
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception:
            return None

    def get_user_id(self, handle: str) -> str | None:
        """Resolve @handle to numeric user ID."""
        data = self._gql(OP_USER_BY_SCREEN_NAME, {"screen_name": handle})
        if not data:
            return None
        try:
            return data["data"]["user"]["result"]["rest_id"]
        except (KeyError, TypeError):
            return None

    def get_tweets(self, user_id: str, count: int = 10) -> list[dict]:
        """Fetch recent tweets for a user ID."""
        data = self._gql(OP_USER_TWEETS, {
            "userId": user_id,
            "count": count,
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": False,
            "withVoice": False,
            "withV2Timeline": True,
        })
        if not data:
            return []

        tweets = []
        try:
            instructions = (
                data["data"]["user"]["result"]["timeline"]
                ["timeline"]["instructions"]
            )
        except (KeyError, TypeError):
            return []

        for inst in instructions:
            if inst.get("type") != "TimelineAddEntries":
                continue
            for entry in inst.get("entries", []):
                tweet_result = (
                    entry.get("content", {})
                    .get("itemContent", {})
                    .get("tweet_results", {})
                    .get("result", {})
                )
                if tweet_result.get("__typename") != "Tweet":
                    continue
                legacy = tweet_result.get("legacy", {})
                if not legacy.get("full_text"):
                    continue
                extracted = self._extract_tweet(tweet_result, legacy)
                if extracted:
                    tweets.append(extracted)
        return tweets

    @staticmethod
    def _extract_tweet(tweet_result: dict, legacy: dict) -> dict:
        """Extract clean tweet data from raw API response. Returns None for RTs."""
        text = legacy.get("full_text", "")
        if text.startswith("RT @"):
            return None  # skip retweets
        return {
            "id": legacy.get("id_str", ""),
            "url": f"https://x.com/i/status/{legacy.get('id_str', '')}",
            "text": text,
            "created_at": legacy.get("created_at", ""),
            "retweet_count": legacy.get("retweet_count", 0),
            "favorite_count": legacy.get("favorite_count", 0),
            "reply_count": legacy.get("reply_count", 0),
            "quote_count": legacy.get("quote_count", 0),
            "view_count": legacy.get("views", {}).get("count", 0)
            if isinstance(legacy.get("views"), dict) else 0,
            "lang": legacy.get("lang", ""),
        }

    def close(self):
        self.client.close()


# ── Collection Logic ─────────────────────────────────────────────────

def is_recent(created_at: str) -> bool:
    """Check if tweet timestamp is within the last 24h."""
    if not created_at:
        return False
    try:
        # Format: "Mon Feb 24 18:58:38 +0000 2025"
        dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
        return dt > CUTOFF
    except (ValueError, TypeError):
        return False


def collect_all(dry_run: bool = False) -> dict:
    """Collect tweets from all monitored profiles."""
    client = XClient()
    output = {
        "coletado_em": datetime.now(timezone.utc).isoformat(),
        "cutoff": CUTOFF.isoformat(),
        "total_perfis": len(PROFILES),
        "perfis_com_dados": 0,
        "perfis_com_erro": 0,
        "total_tweets": 0,
        "perfis": [],
    }

    for i, handle in enumerate(PROFILES, 1):
        print(f"[{i}/{len(PROFILES)}] @{handle} ...", end=" ", flush=True)

        user_id = client.get_user_id(handle)
        if not user_id:
            print("❌ (user not found)")
            output["perfis_com_erro"] += 1
            time.sleep(0.3)
            continue

        all_tweets = client.get_tweets(user_id, count=MAX_TWEETS_PER_USER)
        recent = [t for t in all_tweets if is_recent(t["created_at"])]

        if recent:
            print(f"🟢 {len(recent)} tweets recentes")
        else:
            print(f"⚪ sem tweets nas últimas 24h")

        if all_tweets:
            output["perfis_com_dados"] += 1
            output["total_tweets"] += len(recent)
            output["perfis"].append({
                "handle": handle,
                "user_id": user_id,
                "tweets": recent,
            })
        else:
            output["perfis_com_erro"] += 1

        time.sleep(0.5)  # rate limit

    client.close()

    if dry_run:
        print(f"\n📊 Dry run — {output['total_tweets']} tweets de "
              f"{output['perfis_com_dados']} perfis")
        return output

    # Save full data
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Salvo em {OUTPUT_FILE}")
    print(f"   {output['total_tweets']} tweets de "
          f"{len(output['perfis'])} perfis com dados")

    # Print compact summary for cron job context injection
    print("\n--- COLLECTION_SUMMARY_JSON ---")
    summary = {
        "coletado_em": output["coletado_em"],
        "total_tweets": output["total_tweets"],
        "perfis_ativos": len(output["perfis"]),
        "tweets": [],
    }
    for p in output["perfis"]:
        for t in p["tweets"]:
            t["_source_handle"] = p["handle"]
            summary["tweets"].append(t)
    print(json.dumps(summary, ensure_ascii=False))


def main():
    global OUTPUT_FILE, OUTPUT_DIR
    dry_run = "--dry-run" in sys.argv

    output_path = OUTPUT_FILE
    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i + 1 < len(sys.argv):
            output_path = Path(sys.argv[i + 1])
    OUTPUT_FILE = output_path
    OUTPUT_DIR = output_path.parent

    collect_all(dry_run=dry_run)


if __name__ == "__main__":
    main()
