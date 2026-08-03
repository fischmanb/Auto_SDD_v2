#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-08-03.
Phase 1: Skipped — no predictions file for Aug 2 (gap in daily runs).
Phase 2-5: Simulate tonight's 8 MLB games (Mon trade-deadline slate), produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-08-03"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — SKIPPED (no predictions/2026-08-02.json)
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Skipped (no predictions for 2026-08-02)")
print("=" * 78)
print("  Last prediction file: 2026-07-29. Resuming pipeline without eval.")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (August 3, 2026)
# ═══════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 2-5 — Predicting games for {TODAY}")
print(f"{'=' * 78}")

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers
champ_id = champion["id"]

# ── Tonight's games with odds sourced via web search ──────────────────
# Monday August 3, 2026 — MLB only (NBA/NHL/NFL off-season)
# Limited 8-game slate on trade deadline day.
# Odds from FanDuel, DraftKings, BetMGM, ESPN, Covers, BetRivers.
# Cam Schlittler (NYY, 2.04 ERA) AL Cy Young candidate starts vs STL.
# Michael Lorenzen (COL, 6.54 ERA) at Coors vs TB's Ian Seymour (7-3).
# HOU on 6-game winning streak. Red Sox 8-4 over Dodgers Aug 2.

games_raw = [
    # 1. WAS Nationals @ PHI Phillies — Mon 6:40 PM ET
    # PHI home fav. PHI -156 / WAS +129. O/U 9.5. RL: PHI -1.5.
    # Aaron Nola (PHI, 3-9, 5.61 ERA) vs Andrew Alvarez (WAS).
    # Nola struggling with high ERA despite talent; WAS has solid offense.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.6,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Washington Nationals",
            "season_ppg": 5.0,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.490,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -156,
            "ml_away": 129,
            "total": 9.5,
            "book": "fanduel"
        }
    },

    # 2. STL Cardinals @ NYY Yankees — Mon 7:05 PM ET
    # NYY heavy home fav. NYY -190 / STL +176. O/U 8. RL: NYY -1.5 (+110).
    # Cam Schlittler (NYY, 2.04 ERA, Cy Young candidate) vs Michael McGreevy (STL, 3.57 ERA).
    # Massive pitching mismatch.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Yankees",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.450,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -190,
            "ml_away": 176,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 3. PIT Pirates @ MIL Brewers — Mon 7:40 PM ET
    # MIL home fav. MIL -140 / PIT +130. O/U 8.5. RL: MIL -1.5 (+144).
    # Brandon Sproat (MIL) vs Bubba Chandler (PIT). MIL has best NLC record.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.610,
            "away_record_pct": 0.530,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.450,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -140,
            "ml_away": 130,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 4. LAD Dodgers @ CHC Cubs — Mon 8:05 PM ET
    # LAD slight road fav. LAD -127 / CHC +108. O/U 8. RL: LAD -1.5 (+132).
    # Matthew Boyd (LAD) vs Justin Wrobleski (CHC). Boyd's breakout season.
    # Dodgers best record in NL (.644). Expert lean on CHC ML.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago Cubs",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 4.8,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.660,
            "away_record_pct": 0.570,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 108,
            "ml_away": -127,
            "total": 8.0,
            "book": "betrivers"
        }
    },

    # 5. SF Giants @ TEX Rangers — Mon 8:05 PM ET
    # Pick'em. SF -110 / TEX -110. O/U 8.5. RL: SF -1.5 (+160).
    # Logan Webb (SF) vs Cal Quantrill (TEX). SF struggling (.390).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Texas Rangers",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.440,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "San Francisco Giants",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.430,
            "away_record_pct": 0.370,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -110,
            "ml_away": -110,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 6. TOR Blue Jays @ HOU Astros — Mon 8:10 PM ET
    # HOU slight home fav. HOU -127 / TOR +108. O/U 9. RL: HOU -1.5 (+155).
    # Shane Bieber (TOR) vs Hunter Brown (HOU). HOU on 6-game winning streak.
    # HOU 141 wRC+/.378 wOBA last 6 games despite poor season record.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Houston Astros",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.4,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.420,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.460,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -127,
            "ml_away": 108,
            "total": 9.0,
            "book": "betrivers"
        }
    },

    # 7. TB Rays @ COL Rockies — Mon 8:40 PM ET
    # TB heavy road fav. TB -160 / COL +148. O/U 11.5. RL: TB -1.5 (-110).
    # Ian Seymour (TB, 7-3, 4.37 ERA) vs Michael Lorenzen (COL, 3-9, 6.54 ERA).
    # Coors Field. Rockies worst record in NL (.367), terrible on road (.280).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Colorado Rockies",
            "season_ppg": 4.2,
            "season_opp_ppg": 5.2,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 5.5,
            "season_pace": 1.0,
            "home_record_pct": 0.410,
            "away_record_pct": 0.280,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.540,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 148,
            "ml_away": -160,
            "total": 11.5,
            "book": "fanduel"
        }
    },

    # 8. SD Padres @ ARI Diamondbacks — Mon 9:40 PM ET
    # Near pick'em. SD -106 / ARI -110. O/U 8.5.
    # Michael King (SD) vs Brandon Pfaadt (ARI). Both teams in WC race.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.460,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "San Diego Padres",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.490,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -110,
            "ml_away": -106,
            "total": 8.5,
            "book": "fanduel"
        }
    },
]


# ── Build batch for all models ──────────────────────────────────────
batch = []
for game in games_raw:
    for model in all_models:
        entry = {
            "sport": game["sport"],
            "model_id": model["id"],
            "home": game["home"],
            "away": game["away"],
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000
        }
        batch.append(entry)

print(f"\nRunning {len(batch)} simulations ({len(games_raw)} games x {len(all_models)} models)...")
results = run_batch(batch)
print(f"  Simulations complete.")

# ── Organize results by game ──────────────────────────────────────
game_results = {}
idx = 0
for game in games_raw:
    game_name = f"{game['away']['name']} @ {game['home']['name']}"
    game_results[game_name] = {
        "game_data": game,
        "model_results": {}
    }
    for model in all_models:
        game_results[game_name]["model_results"][model["id"]] = results[idx]
        idx += 1

# ── Blended predictions ──────────────────────────────────────────
predictions = []

for game_name, gd in game_results.items():
    game = gd["game_data"]
    mr = gd["model_results"]

    total_weight = 1.0
    blend_home_wp = mr[champ_id]["home_win_prob"] * 1.0
    blend_spread_ev_home = mr[champ_id]["spread_ev_home"] * 1.0
    blend_spread_ev_away = mr[champ_id]["spread_ev_away"] * 1.0
    blend_ml_ev_home = mr[champ_id]["ml_ev_home"] * 1.0
    blend_ml_ev_away = mr[champ_id]["ml_ev_away"] * 1.0

    for c in challengers:
        cid = c["id"]
        w = c["weight"]
        total_weight += w
        blend_home_wp += mr[cid]["home_win_prob"] * w
        blend_spread_ev_home += mr[cid]["spread_ev_home"] * w
        blend_spread_ev_away += mr[cid]["spread_ev_away"] * w
        blend_ml_ev_home += mr[cid]["ml_ev_home"] * w
        blend_ml_ev_away += mr[cid]["ml_ev_away"] * w

    blend_home_wp /= total_weight
    blend_spread_ev_home /= total_weight
    blend_spread_ev_away /= total_weight
    blend_ml_ev_home /= total_weight
    blend_ml_ev_away /= total_weight
    blend_away_wp = 1.0 - blend_home_wp
    blend_margin = sum(mr[m["id"]]["expected_margin"] * (1.0 if m["id"] == champ_id else next(c["weight"] for c in challengers if c["id"] == m["id"])) for m in all_models) / total_weight

    ev_options = [
        ("spread_home", blend_spread_ev_home),
        ("spread_away", blend_spread_ev_away),
        ("ml_home", blend_ml_ev_home),
        ("ml_away", blend_ml_ev_away),
    ]
    best_bet_type, best_blend_ev = max(ev_options, key=lambda x: x[1])

    model_evs_for_best = []
    for m in all_models:
        mid = m["id"]
        if best_bet_type == "spread_home":
            model_evs_for_best.append(mr[mid]["spread_ev_home"])
        elif best_bet_type == "spread_away":
            model_evs_for_best.append(mr[mid]["spread_ev_away"])
        elif best_bet_type == "ml_home":
            model_evs_for_best.append(mr[mid]["ml_ev_home"])
        else:
            model_evs_for_best.append(mr[mid]["ml_ev_away"])

    best_model_ev = max(model_evs_for_best)
    worst_model_ev = min(model_evs_for_best)

    if "home" in best_bet_type:
        agree_count = sum(1 for m in all_models if mr[m["id"]]["home_win_prob"] > 0.5)
        side = "HOME"
        side_team = game["home"]["name"]
    else:
        agree_count = sum(1 for m in all_models if mr[m["id"]]["home_win_prob"] <= 0.5)
        side = "AWAY"
        side_team = game["away"]["name"]

    robustness = f"{agree_count}/6"

    if best_blend_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_blend_ev > 0.015 and agree_count < 4:
        verdict = "LEAN"
    elif best_blend_ev > 0.015 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    else:
        verdict = "NO BET"

    if verdict == "BET" and worst_model_ev < 0:
        verdict = "LEAN"

    if best_blend_ev > 0:
        kelly = min(0.05, best_blend_ev / (best_model_ev if best_model_ev > 0 else 1.0))
    else:
        kelly = 0.0

    bet_market = "SPREAD" if "spread" in best_bet_type else "ML"

    pred_entry = {
        "game": game_name,
        "sport": game["sport"],
        "home_team": game["home"]["name"],
        "away_team": game["away"]["name"],
        "odds": game["odds"],
        "blend_home_wp": round(blend_home_wp, 4),
        "blend_away_wp": round(blend_away_wp, 4),
        "blend_margin": round(blend_margin, 2),
        "best_bet_type": best_bet_type,
        "best_blend_ev": round(best_blend_ev, 4),
        "best_model_ev": round(best_model_ev, 4),
        "worst_model_ev": round(worst_model_ev, 4),
        "robustness": robustness,
        "agree_count": agree_count,
        "verdict": verdict,
        "side": side,
        "side_team": side_team,
        "bet_market": bet_market,
        "kelly": round(kelly, 4),
        "model_results": {
            mid: {
                "home_win_prob": mr[mid]["home_win_prob"],
                "expected_margin": mr[mid]["expected_margin"],
                "spread_ev_home": mr[mid]["spread_ev_home"],
                "spread_ev_away": mr[mid]["spread_ev_away"],
                "ml_ev_home": mr[mid]["ml_ev_home"],
                "ml_ev_away": mr[mid]["ml_ev_away"],
            }
            for mid in [m["id"] for m in all_models]
        }
    }
    predictions.append(pred_entry)

# ── Save predictions ──────────────────────────────────────────────
output = {
    "date": TODAY,
    "predictions": predictions,
    "metadata": {
        "sports_checked": ["baseball_mlb"],
        "sports_skipped": [
            "basketball_nba (off-season)",
            "icehockey_nhl (off-season)",
            "americanfootball_nfl (preseason, no games)"
        ],
        "total_games": len(predictions),
        "total_bets": sum(1 for p in predictions if p["verdict"] == "BET"),
        "total_leans": sum(1 for p in predictions if p["verdict"] == "LEAN"),
        "data_sources": [
            "web search (ESPN, FanDuel, DraftKings, BetMGM, BetRivers, Covers, NBC Sports, Yahoo Sports, Baseball-Reference)"
        ],
        "note": "ODDS_API_KEY not configured; odds sourced from web search. Mon 8-game trade-deadline-day slate. Phase 1 eval skipped (no Aug 2 predictions). BOS beat LAD 8-4 Aug 2."
    }
}

with open(os.path.join(BASE, "predictions", f"{TODAY}.json"), "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Predictions saved to predictions/{TODAY}.json")

# ── Update metrics ──────────────────────────────────────────────────
with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

metrics["last_updated"] = TODAY

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": output["metadata"]["total_bets"],
    "leans": output["metadata"]["total_leans"],
    "sports": ["baseball_mlb"],
    "notes": f"MLB Mon trade deadline slate (8 games). No Phase 1 eval (gap since Jul 29). Schlittler (2.04 ERA) starts NYY vs STL. Coors Field TB@COL (O/U 11.5)."
}

metrics["variant_performance"] = {
    m["id"]: {
        "lifetime_games": m.get("lifetime_games", 0),
        "lifetime_correct": m.get("lifetime_correct", 0),
        "weight": 1.0 if m["id"] == champ_id else m.get("weight", 0.5),
        "role": "champion" if m["id"] == champ_id else "challenger"
    }
    for m in all_models
}

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)
print(f"  Metrics updated.")

# ── Display results ──────────────────────────────────────────────────
print(f"\n{'=' * 78}")
print(f" RESULTS — MLB Monday Aug 3, 2026 (Trade Deadline Day)")
print(f"{'=' * 78}")
print(f"{'Game':<28} {'Spread':>7} {'Blend EV':>9} {'Best EV':>8} {'Worst':>6} {'Rob.':>5} {'Verdict':<14}")
print("-" * 78)

bets = []
leans = []
no_bets = []

for p in predictions:
    short_away = p["away_team"].split()[-1][:5]
    short_home = p["home_team"].split()[-1][:5]
    spread = p["odds"]["spread_home"]
    game_label = f"{short_away} @ {short_home} ({spread:+.1f})"

    line = f"{game_label:<28} {spread:>+7.1f} {p['best_blend_ev']:>+9.1%} {p['best_model_ev']:>+8.1%} {p['worst_model_ev']:>+6.1%} {p['robustness']:>5} "

    if p["verdict"] == "BET":
        line += f"{'BET ' + p['side']:<14}"
        bets.append(p)
    elif p["verdict"] == "LEAN":
        line += f"{'LEAN ' + p['side']:<14}"
        leans.append(p)
    else:
        line += f"{'NO BET':<14}"
        no_bets.append(p)

    print(line)

print(f"\n  SUMMARY: {len(bets)} BETs, {len(leans)} LEANs, {len(no_bets)} NO BETs out of {len(predictions)} games")

if bets:
    print(f"\n{'=' * 78}")
    print(f" BET DETAILS")
    print(f"{'=' * 78}")
    for p in bets:
        print(f"\n  {p['game']}")
        print(f"    Side: {p['side']} ({p['side_team']})")
        print(f"    Market: {p['bet_market']} | Spread: {p['odds']['spread_home']:+.1f}")
        print(f"    Blend EV: {p['best_blend_ev']:+.1%} | Best: {p['best_model_ev']:+.1%} | Worst: {p['worst_model_ev']:+.1%}")
        print(f"    Robustness: {p['robustness']} | Kelly: {p['kelly']:.1%}")
        print(f"    Book: {p['odds']['book']}")
        print(f"    Model breakdown:")
        for mid, mr in p["model_results"].items():
            role = "CHAMP" if mid == champ_id else f"w={next(c['weight'] for c in challengers if c['id'] == mid)}"
            wp = mr["home_win_prob"] if p["side"] == "HOME" else 1 - mr["home_win_prob"]
            if p["best_bet_type"] == "spread_home":
                ev = mr["spread_ev_home"]
            elif p["best_bet_type"] == "spread_away":
                ev = mr["spread_ev_away"]
            elif p["best_bet_type"] == "ml_home":
                ev = mr["ml_ev_home"]
            else:
                ev = mr["ml_ev_away"]
            agree = "Y" if (mr["home_win_prob"] > 0.5) == (p["side"] == "HOME") else "N"
            print(f"      {mid:<20} WP={wp:.1%} EV={ev:+.1%} agree={agree} [{role}]")

if leans:
    print(f"\n{'=' * 78}")
    print(f" LEAN DETAILS")
    print(f"{'=' * 78}")
    for p in leans:
        print(f"\n  {p['game']}")
        print(f"    Side: {p['side']} ({p['side_team']})")
        print(f"    Market: {p['bet_market']} | Blend EV: {p['best_blend_ev']:+.1%} | Rob: {p['robustness']}")

# ── Metrics dashboard ──────────────────────────────────────────────
print(f"\n{'=' * 78}")
print(f" METRICS DASHBOARD")
print(f"{'=' * 78}")
print(f"  Champion: {champ_id}")
print(f"  All-time: {champion.get('lifetime_games', 0)} games, {champion.get('lifetime_correct', 0)} correct ({champion.get('lifetime_correct', 0)/max(champion.get('lifetime_games', 1), 1)*100:.1f}%)")
challenger_strs = [f"{c['id']}={c['weight']}" for c in challengers]
print(f"  Challenger weights: {', '.join(challenger_strs)}")
if assumptions.get("graveyard"):
    grave_strs = [g['id'] + ' (died ' + g['died'] + ')' for g in assumptions['graveyard']]
    print(f"  Graveyard: {', '.join(grave_strs)}")

print(f"\n  NOTE: This is for entertainment and analysis purposes only.")
print(f"  Past performance does not guarantee future results.")
print(f"  All values based on $100 unit bets.")
