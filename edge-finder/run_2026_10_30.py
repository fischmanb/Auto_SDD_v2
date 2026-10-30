#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-10-30 (Friday).
Phase 1 (eval Oct 29) already done by session eval script.
Phase 2-5: Simulate tonight's games:
  - 10 NBA (Day 11 of 2026-27, NBA Cup opening night)
  - 3 NHL
  = 13 games total.

Sports context:
  NFL: No game Friday. CAR @ GB TNF last night.
  MLB: World Series over (MIL swept TB 4-0).
  NBA: HOU 5-0 best start. MEM 5-0. DET 5-1. BOS elite 6-1. NOP got first win last night.
        NBA Cup group stage begins tonight (6 of 10 games are Cup games).
  NHL: WPG on 7-game losing streak, Morrissey out. NJD acquired Hellebuyck.
       TB 8-3-1 unbeaten at home. CAR 11-2-2 dominant.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-10-30"

# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION (Tonight's games: Oct 30, 2026)
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(f" PHASE 2 — Collecting data for {TODAY}")
print("=" * 78)
print("  Odds sourced from web search: FanDuel, DraftKings, Yahoo Sports, ESPN,")
print("  CBS Sports, BetMGM, Covers, SportsBettingDime, Dimers, OtterLine.")

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

tonight_games = []

# ── NBA (10 games — NBA Cup opening night + regular season) ──

nba_games = [
    # 1. Charlotte Hornets @ Washington Wizards — two bad teams, WAS slight home fav
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Washington Wizards", "season_ppg": 108.5, "season_opp_ppg": 118.0,
            "last10_ppg": 108.5, "last10_opp_ppg": 118.0,
            "season_pace": 100.0, "home_record_pct": 0.40, "away_record_pct": 0.25,
            "is_back_to_back": False, "key_injuries": 2
        },
        "away": {
            "name": "Charlotte Hornets", "season_ppg": 107.0, "season_opp_ppg": 113.5,
            "last10_ppg": 107.0, "last10_opp_ppg": 113.5,
            "season_pace": 98.5, "home_record_pct": 0.33, "away_record_pct": 0.25,
            "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {
            "spread_home": -2.0, "ml_home": -118, "ml_away": 100,
            "total": 218.5, "book": "DraftKings"
        }
    },
    # 2. Chicago Bulls @ Boston Celtics — BOS huge favorite at home
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Boston Celtics", "season_ppg": 122.0, "season_opp_ppg": 107.0,
            "last10_ppg": 125.0, "last10_opp_ppg": 104.0,
            "season_pace": 101.5, "home_record_pct": 0.83, "away_record_pct": 0.75,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Chicago Bulls", "season_ppg": 114.0, "season_opp_ppg": 120.0,
            "last10_ppg": 115.0, "last10_opp_ppg": 122.0,
            "season_pace": 100.5, "home_record_pct": 0.33, "away_record_pct": 0.20,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -8.5, "ml_home": -350, "ml_away": 280,
            "total": 226.5, "book": "DraftKings"
        }
    },
    # 3. Detroit Pistons @ Brooklyn Nets — DET surprise contender, BKN tanking
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Brooklyn Nets", "season_ppg": 108.5, "season_opp_ppg": 118.5,
            "last10_ppg": 108.0, "last10_opp_ppg": 119.0,
            "season_pace": 99.0, "home_record_pct": 0.25, "away_record_pct": 0.20,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Detroit Pistons", "season_ppg": 104.5, "season_opp_ppg": 98.0,
            "last10_ppg": 104.0, "last10_opp_ppg": 97.5,
            "season_pace": 96.0, "home_record_pct": 0.80, "away_record_pct": 0.67,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": 7.5, "ml_home": 220, "ml_away": -270,
            "total": 215.5, "book": "DraftKings"
        }
    },
    # 4. Orlando Magic @ Toronto Raptors — TOR slight home fav
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Toronto Raptors", "season_ppg": 109.0, "season_opp_ppg": 112.0,
            "last10_ppg": 110.0, "last10_opp_ppg": 113.0,
            "season_pace": 99.5, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Orlando Magic", "season_ppg": 108.0, "season_opp_ppg": 107.5,
            "last10_ppg": 107.0, "last10_opp_ppg": 108.0,
            "season_pace": 98.0, "home_record_pct": 0.50, "away_record_pct": 0.40,
            "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {
            "spread_home": -2.5, "ml_home": -140, "ml_away": 120,
            "total": 219.5, "book": "FanDuel"
        }
    },
    # 5. New York Knicks @ Philadelphia 76ers — close matchup, PHI slight fav
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Philadelphia 76ers", "season_ppg": 113.5, "season_opp_ppg": 111.0,
            "last10_ppg": 114.0, "last10_opp_ppg": 112.0,
            "season_pace": 99.5, "home_record_pct": 0.50, "away_record_pct": 0.40,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "New York Knicks", "season_ppg": 114.0, "season_opp_ppg": 112.5,
            "last10_ppg": 115.0, "last10_opp_ppg": 114.0,
            "season_pace": 100.5, "home_record_pct": 0.60, "away_record_pct": 0.40,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -125, "ml_away": 106,
            "total": 228.5, "book": "FanDuel"
        }
    },
    # 6. Indiana Pacers @ Miami Heat — MIA home fav, pace mismatch
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Miami Heat", "season_ppg": 112.0, "season_opp_ppg": 108.0,
            "last10_ppg": 113.0, "last10_opp_ppg": 107.0,
            "season_pace": 98.5, "home_record_pct": 0.60, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Indiana Pacers", "season_ppg": 119.5, "season_opp_ppg": 115.0,
            "last10_ppg": 120.0, "last10_opp_ppg": 116.0,
            "season_pace": 103.0, "home_record_pct": 0.50, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": -2.5, "ml_home": -140, "ml_away": 120,
            "total": 222.0, "book": "FanDuel"
        }
    },
    # 7. LA Clippers @ Minnesota Timberwolves — MIN big home fav
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Minnesota Timberwolves", "season_ppg": 115.0, "season_opp_ppg": 108.0,
            "last10_ppg": 116.0, "last10_opp_ppg": 107.0,
            "season_pace": 100.0, "home_record_pct": 0.75, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Clippers", "season_ppg": 106.0, "season_opp_ppg": 113.0,
            "last10_ppg": 105.0, "last10_opp_ppg": 114.0,
            "season_pace": 98.0, "home_record_pct": 0.33, "away_record_pct": 0.25,
            "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {
            "spread_home": -7.5, "ml_home": -260, "ml_away": 215,
            "total": 222.5, "book": "FanDuel"
        }
    },
    # 8. Houston Rockets @ Dallas Mavericks — HOU road fav, 5-0 start
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Dallas Mavericks", "season_ppg": 113.0, "season_opp_ppg": 110.5,
            "last10_ppg": 115.0, "last10_opp_ppg": 108.0,
            "season_pace": 100.0, "home_record_pct": 0.60, "away_record_pct": 0.40,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Houston Rockets", "season_ppg": 121.0, "season_opp_ppg": 106.5,
            "last10_ppg": 123.0, "last10_opp_ppg": 105.0,
            "season_pace": 101.0, "home_record_pct": 0.80, "away_record_pct": 0.75,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": 6.5, "ml_home": 176, "ml_away": -210,
            "total": 227.5, "book": "FanDuel"
        }
    },
    # 9. Denver Nuggets @ Phoenix Suns — PHX slight home fav
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Phoenix Suns", "season_ppg": 117.0, "season_opp_ppg": 112.0,
            "last10_ppg": 118.0, "last10_opp_ppg": 113.0,
            "season_pace": 101.0, "home_record_pct": 0.60, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Denver Nuggets", "season_ppg": 119.0, "season_opp_ppg": 113.5,
            "last10_ppg": 118.0, "last10_opp_ppg": 115.0,
            "season_pace": 100.5, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": -2.5, "ml_home": -145, "ml_away": 125,
            "total": 231.0, "book": "FanDuel"
        }
    },
    # 10. LA Lakers @ Golden State Warriors — LAL road fav
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Golden State Warriors", "season_ppg": 116.0, "season_opp_ppg": 113.0,
            "last10_ppg": 117.0, "last10_opp_ppg": 114.0,
            "season_pace": 101.5, "home_record_pct": 0.50, "away_record_pct": 0.40,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Lakers", "season_ppg": 112.5, "season_opp_ppg": 106.5,
            "last10_ppg": 113.0, "last10_opp_ppg": 105.0,
            "season_pace": 100.0, "home_record_pct": 0.67, "away_record_pct": 0.60,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": 2.5, "ml_home": 124, "ml_away": -146,
            "total": 234.5, "book": "Yahoo Sports"
        }
    },
]

# ── NHL (3 games) ──

nhl_games = [
    # 1. New Jersey Devils @ Vegas Golden Knights — VGK home fav
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Vegas Golden Knights", "season_ppg": 3.4, "season_opp_ppg": 2.5,
            "last10_ppg": 3.5, "last10_opp_ppg": 2.4,
            "season_pace": 1.0, "home_record_pct": 0.75, "away_record_pct": 0.60,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "New Jersey Devils", "season_ppg": 3.3, "season_opp_ppg": 2.6,
            "last10_ppg": 3.4, "last10_opp_ppg": 2.5,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.55,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -145, "ml_away": 125,
            "total": 6.0, "book": "DraftKings"
        }
    },
    # 2. Winnipeg Jets @ Florida Panthers — FLA home fav, WPG slumping hard
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Florida Panthers", "season_ppg": 3.2, "season_opp_ppg": 2.4,
            "last10_ppg": 3.3, "last10_opp_ppg": 2.3,
            "season_pace": 1.0, "home_record_pct": 0.75, "away_record_pct": 0.60,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Winnipeg Jets", "season_ppg": 2.6, "season_opp_ppg": 3.0,
            "last10_ppg": 2.4, "last10_opp_ppg": 3.2,
            "season_pace": 1.0, "home_record_pct": 0.33, "away_record_pct": 0.30,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -165, "ml_away": 140,
            "total": 6.0, "book": "BetMGM"
        }
    },
    # 3. Seattle Kraken @ Calgary Flames — CGY home fav
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Calgary Flames", "season_ppg": 3.1, "season_opp_ppg": 2.7,
            "last10_ppg": 3.2, "last10_opp_ppg": 2.6,
            "season_pace": 1.0, "home_record_pct": 0.60, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Seattle Kraken", "season_ppg": 2.8, "season_opp_ppg": 3.0,
            "last10_ppg": 2.7, "last10_opp_ppg": 3.1,
            "season_pace": 1.0, "home_record_pct": 0.40, "away_record_pct": 0.35,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -125, "ml_away": 105,
            "total": 6.5, "book": "SportsBettingDime"
        }
    },
]

tonight_games = nba_games + nhl_games
print(f"  Tonight: {len(nba_games)} NBA + {len(nhl_games)} NHL = {len(tonight_games)} games")

# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — SIMULATE (Champion + 5 Challengers)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 3 — Running simulations (6 models × {len(tonight_games)} games = {6 * len(tonight_games)} sims)")
print("=" * 78)

champ = assumptions["champion"]
challengers = assumptions["challengers"]
all_model_defs = [champ] + challengers

batch = []
for game in tonight_games:
    for model in all_model_defs:
        sim_input = {
            "sport": game["sport"],
            "model_id": model["id"],
            "home": game["home"],
            "away": game["away"],
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000
        }
        batch.append(sim_input)

print(f"  Running {len(batch)} simulations...")
results = run_batch(batch)
print(f"  ✓ All {len(results)} simulations complete")

# Group results by game
game_results = {}
for i, r in enumerate(results):
    game_idx = i // 6
    model_idx = i % 6
    if game_idx not in game_results:
        game_results[game_idx] = {}
    model_id = all_model_defs[model_idx]["id"]
    game_results[game_idx][model_id] = r

# ════════════════════════════════════════════════════════════════════════
# PHASE 4 — BLENDED PREDICTION + OUTPUT
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 4 — Blended predictions for {TODAY}")
print("=" * 78)

predictions = []

for gi, game in enumerate(tonight_games):
    model_preds = game_results[gi]

    weights = {}
    weights[champ["id"]] = 1.0
    for c in challengers:
        weights[c["id"]] = c["weight"]

    total_weight = sum(weights.values())
    blend_hwp = sum(model_preds[mid]["home_win_prob"] * weights[mid] for mid in weights) / total_weight
    blend_awp = 1.0 - blend_hwp
    blend_margin = sum(model_preds[mid]["expected_margin"] * weights[mid] for mid in weights) / total_weight

    ev_keys = ["spread_ev_home", "spread_ev_away", "ml_ev_home", "ml_ev_away"]
    blend_evs = {}
    for k in ev_keys:
        blend_evs[k] = sum(model_preds[mid][k] * weights[mid] for mid in weights) / total_weight

    best_bet_key = max(blend_evs, key=blend_evs.get)
    best_ev = blend_evs[best_bet_key]

    best_model_ev = max(model_preds[mid][best_bet_key] for mid in weights)
    worst_model_ev = min(model_preds[mid][best_bet_key] for mid in weights)

    home_side = blend_hwp > 0.5
    agree_count = sum(1 for mid in weights if (model_preds[mid]["home_win_prob"] > 0.5) == home_side)

    if best_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_ev > 0.015 and agree_count < 4:
        verdict = "LEAN"
    else:
        any_flip = any(model_preds[mid][best_bet_key] < 0 for mid in weights)
        if any_flip or best_ev < 0.015:
            verdict = "NO BET"
        elif best_ev > 0.015:
            verdict = "LEAN"
        else:
            verdict = "NO BET"

    kelly_half = 0
    if best_ev > 0:
        bet_side_key = "ml_home" if "home" in best_bet_key else "ml_away"
        ml_val = game["odds"][bet_side_key]
        if ml_val > 0:
            b = ml_val / 100.0
        else:
            b = 100.0 / abs(ml_val)
        p = blend_hwp if "home" in best_bet_key else blend_awp
        kelly = (b * p - (1 - p)) / b if b > 0 else 0
        kelly_half = round(max(0, kelly / 2), 3)

    pred_entry = {
        "sport": game["sport"],
        "home": game["home"]["name"],
        "away": game["away"]["name"],
        "odds": game["odds"],
        "blended": {
            "home_win_prob": round(blend_hwp, 4),
            "away_win_prob": round(blend_awp, 4),
            "expected_margin": round(blend_margin, 2),
            "best_ev": round(best_ev, 4),
            "best_bet": best_bet_key,
            "robustness": agree_count,
            "verdict": verdict,
            "kelly_half": kelly_half,
            "best_model_ev": round(best_model_ev, 4),
            "worst_model_ev": round(worst_model_ev, 4),
        },
        "model_predictions": {}
    }
    for mid in weights:
        mp = model_preds[mid]
        pred_entry["model_predictions"][mid] = {
            "home_win_prob": mp["home_win_prob"],
            "ml_ev_home": mp["ml_ev_home"],
            "ml_ev_away": mp["ml_ev_away"],
            "spread_ev_home": mp["spread_ev_home"],
            "spread_ev_away": mp["spread_ev_away"],
            "expected_margin": mp["expected_margin"],
        }

    predictions.append(pred_entry)

# ── Save predictions FIRST ──
pred_output = {
    "date": TODAY,
    "sports": sorted(set(g["sport"] for g in tonight_games)),
    "context": (
        f"Friday Oct 30: {len(nba_games)} NBA (Cup opening night) + {len(nhl_games)} NHL = "
        f"{len(tonight_games)} games. Champion: {champ['id']}. "
        "Oct 29 eval: 7/14 ML (50.0%). Rough night, all NBA wrong. "
        "Headlines: ATL upset CLE, NOP first win vs SAC, MEM 5-0 beat POR. "
        "NHL: SJS stunned VAN, MTL 5-2 DAL, NYI OT win at MIN. "
        "HOU 5-0 best NBA start. WPG on 7-game skid. NJD has Hellebuyck."
    ),
    "note": "Odds sourced from FanDuel, DraftKings, Yahoo Sports, ESPN, BetMGM, SportsBettingDime, Dimers, OtterLine.",
    "games": predictions
}

pred_path = os.path.join(BASE, "predictions", f"{TODAY}.json")
with open(pred_path, "w") as f:
    json.dump(pred_output, f, indent=2)
    f.write("\n")
print(f"\n  ✓ Predictions saved to predictions/{TODAY}.json")

# ── Display results ──
sport_names = {
    "basketball_nba": "NBA",
    "icehockey_nhl": "NHL",
}

verdict_icons = {"BET": "✅", "LEAN": "⚠️", "NO BET": "❌"}

for sport_key in sorted(set(g["sport"] for g in tonight_games)):
    sport_preds = [p for p in predictions if p["sport"] == sport_key]
    if not sport_preds:
        continue

    sport_label = sport_names.get(sport_key, sport_key)
    print(f"\n┌{'─' * 77}┐")
    print(f"│ {sport_label} — Friday Oct 30, 2026{' ' * (77 - len(sport_label) - 24)}│")
    print(f"├{'─' * 20}┬{'─' * 8}┬{'─' * 8}┬{'─' * 8}┬{'─' * 7}┬{'─' * 6}┬{'─' * 15}┤")
    print(f"│ {'Game':<18} │ {'Spread':>6} │ {'Blend':>6} │ {'Best':>6} │ {'Worst':>5} │ {'Rob.':>4} │ {'Verdict':>13} │")
    print(f"│ {'':18} │ {'':>6} │ {'EV':>6} │ {'EV':>6} │ {'EV':>5} │ {'':>4} │ {'':>13} │")
    print(f"├{'─' * 20}┼{'─' * 8}┼{'─' * 8}┼{'─' * 8}┼{'─' * 7}┼{'─' * 6}┼{'─' * 15}┤")

    for p in sport_preds:
        b = p["blended"]
        spread = p["odds"]["spread_home"]
        home_short = p["home"].split()[-1][:10]
        away_short = p["away"].split()[-1][:10]

        if spread < 0:
            game_str = f"{home_short} {spread}"
        elif spread > 0:
            game_str = f"{away_short} {-spread}"
        else:
            game_str = f"{home_short} PK"

        side = "HOME" if b["home_win_prob"] > 0.5 else "AWAY"
        icon = verdict_icons.get(b["verdict"], "")
        verdict_str = f"{icon} {b['verdict']} {side}"

        print(f"│ {game_str:<18} │ {spread:>+6.1f} │ {b['best_ev']:>+5.1%} │ "
              f"{b['best_model_ev']:>+5.1%} │ {b['worst_model_ev']:>+4.1%} │ "
              f"{b['robustness']:>2}/6 │ {verdict_str:>13} │")

    print(f"└{'─' * 20}┴{'─' * 8}┴{'─' * 8}┴{'─' * 8}┴{'─' * 7}┴{'─' * 6}┴{'─' * 15}┘")

    # Show BET details
    bets = [p for p in sport_preds if p["blended"]["verdict"] == "BET"]
    for p in bets:
        b = p["blended"]
        print(f"\n  📌 {p['home']} vs {p['away']}")
        print(f"     Best line: {p['odds']['book']} | Best bet: {b['best_bet'].replace('_', ' ')}")
        print(f"     Kelly half: {b['kelly_half']:.1%} of bankroll")
        agree = [mid for mid in p["model_predictions"]
                 if (p["model_predictions"][mid]["home_win_prob"] > 0.5) == (b["home_win_prob"] > 0.5)]
        disagree = [mid for mid in p["model_predictions"] if mid not in agree]
        print(f"     Agree ({len(agree)}): {', '.join(agree)}")
        if disagree:
            print(f"     Disagree ({len(disagree)}): {', '.join(disagree)}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 5 — Metrics Dashboard")
print("=" * 78)

with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

# Count bets
bet_count = sum(1 for p in predictions if p["blended"]["verdict"] == "BET")
lean_count = sum(1 for p in predictions if p["blended"]["verdict"] == "LEAN")
no_bet_count = sum(1 for p in predictions if p["blended"]["verdict"] == "NO BET")

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": bet_count,
    "leans": lean_count,
    "no_bets": no_bet_count,
    "sports": sorted(set(g["sport"] for g in tonight_games)),
    "notes": (
        f"Oct 29 eval: 7/14 ML (50.0%). Rough night. "
        f"Tonight: {len(nba_games)} NBA + {len(nhl_games)} NHL = "
        f"{len(tonight_games)} games. NBA Cup opening night. "
        "Key: HOU 5-0, WPG 7-game skid, NJD Hellebuyck debut potential."
    )
}
metrics["last_updated"] = TODAY

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)
    f.write("\n")

# Print summary
print(f"\n📊 Edge-Finder Metrics")
print("━" * 40)
print(f"Champion: {champ['id']} (promoted {champ.get('promoted_on', 'N/A')})")
r7 = metrics["rolling_7d"]
r30 = metrics["rolling_30d"]
print(f"7-day:  {r7['accuracy']:.0%} accuracy | +{r7['ev_realized']:.1%} realized EV | {r7['total_games']} games")
print(f"30-day: {r30['accuracy']:.0%} accuracy | +{r30['ev_realized']:.1%} realized EV | {r30['total_games']} games")
print()
chall_str = ", ".join(f"{c['id']}={c['weight']:.1f}" for c in challengers)
print(f"Challenger weights: {chall_str}")
for g in assumptions.get("graveyard", []):
    print(f"Graveyard: {g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%} accuracy)")
print()
print(f"Tonight: {len(predictions)} games analyzed, {bet_count} BETs, {lean_count} LEANs, {no_bet_count} NO BETs")
print()

# Disclaimer
print("⚠️  DISCLAIMER: This is for entertainment and analysis purposes only.")
print("    Past performance does not guarantee future results.")
print("    Always gamble responsibly.")
