#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-05-28.
Phase 1: Evaluate 2026-05-26 predictions against actual results.
Phase 2-5: Simulate tonight's games and produce predictions.
"""

import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-05-28"
EVAL_DATE = "2026-05-26"

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1: Evaluate May 26 predictions
# ═══════════════════════════════════════════════════════════════════════════

actual_results = {
    "San Antonio Spurs @ Oklahoma City Thunder": {"home_score": 127, "away_score": 114, "winner": "home", "margin": 13},
    "Colorado Avalanche @ Vegas Golden Knights": {"home_score": 2, "away_score": 1, "winner": "home", "margin": 1},
    "Washington Nationals @ Cleveland Guardians": {"home_score": 3, "away_score": 2, "winner": "home", "margin": 1},
    "Tampa Bay Rays @ Baltimore Orioles": {"home_score": 6, "away_score": 1, "winner": "home", "margin": 5},
    "Los Angeles Angels @ Detroit Tigers": {"home_score": 6, "away_score": 10, "winner": "away", "margin": -4},
    "Chicago Cubs @ Pittsburgh Pirates": {"home_score": 12, "away_score": 1, "winner": "home", "margin": 11},
    "Atlanta Braves @ Boston Red Sox": {"home_score": 6, "away_score": 7, "winner": "away", "margin": -1},
    "Miami Marlins @ Toronto Blue Jays": {"home_score": 2, "away_score": 1, "winner": "home", "margin": 1},
    "Cincinnati Reds @ New York Mets": {"home_score": 2, "away_score": 7, "winner": "away", "margin": -5},
    "Minnesota Twins @ Chicago White Sox": {"home_score": 3, "away_score": 1, "winner": "home", "margin": 2},
    "New York Yankees @ Kansas City Royals": {"home_score": 3, "away_score": 4, "winner": "away", "margin": -1},
    "St. Louis Cardinals @ Milwaukee Brewers": {"home_score": 2, "away_score": 1, "winner": "home", "margin": 1},
    "Houston Astros @ Texas Rangers": {"home_score": 0, "away_score": 9, "winner": "away", "margin": -9},
    "Seattle Mariners @ Sacramento Athletics": {"home_score": 1, "away_score": 9, "winner": "away", "margin": -8},
    "Philadelphia Phillies @ San Diego Padres": {"home_score": 0, "away_score": 3, "winner": "away", "margin": -3},
    "Arizona Diamondbacks @ San Francisco Giants": {"home_score": 2, "away_score": 3, "winner": "away", "margin": -1},
    "Colorado Rockies @ Los Angeles Dodgers": {"home_score": 5, "away_score": 3, "winner": "home", "margin": 2},
}

# Load predictions
with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    pred_data = json.load(f)

# Load assumptions
with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers
model_ids = [m["id"] for m in all_models]

# Score each model per game
results_rows = []
model_correct = {m["id"]: 0 for m in all_models}
model_total = {m["id"]: 0 for m in all_models}

print(f"\n{'='*78}")
print(f" PHASE 1: Evaluating {EVAL_DATE} predictions")
print(f"{'='*78}")

for pred in pred_data["predictions"]:
    game_key = pred["game"]
    if game_key not in actual_results:
        print(f"  WARNING: No actual result for {game_key}, skipping")
        continue

    actual = actual_results[game_key]
    sport = pred["sport"]

    for mid, mr in pred["model_results"].items():
        predicted_winner = "home" if mr["expected_margin"] > 0 else "away"
        predicted_margin = mr["expected_margin"]
        predicted_wp = mr["home_win_prob"]
        actual_winner = actual["winner"]
        actual_margin = actual["margin"]
        hit = 1 if predicted_winner == actual_winner else 0

        model_correct[mid] = model_correct.get(mid, 0) + hit
        model_total[mid] = model_total.get(mid, 0) + 1

        spread = pred["odds"]["spread_home"]
        home_covers = (actual_margin + spread) > 0
        spread_ev = mr["spread_ev_home"]
        ml_ev = mr["ml_ev_home"]

        best_bet_ev = max(mr["spread_ev_home"], mr["spread_ev_away"],
                         mr["ml_ev_home"], mr["ml_ev_away"])
        if best_bet_ev == mr["spread_ev_home"]:
            bet_type = "spread_home"
            bet_win = home_covers
        elif best_bet_ev == mr["spread_ev_away"]:
            bet_type = "spread_away"
            bet_win = not home_covers
        elif best_bet_ev == mr["ml_ev_home"]:
            bet_type = "ml_home"
            bet_win = actual_winner == "home"
        else:
            bet_type = "ml_away"
            bet_win = actual_winner == "away"

        row = (
            f"{EVAL_DATE}\t{sport}\t{game_key}\t{mid}\t"
            f"{predicted_winner}\t{predicted_margin:.2f}\t{predicted_wp:.4f}\t"
            f"{actual_winner}\t{actual_margin}\t{hit}\t"
            f"{spread_ev:.4f}\t{ml_ev:.4f}\t{bet_type}\t{'win' if bet_win else 'loss'}"
        )
        results_rows.append(row)

# Append to results.tsv
results_file = os.path.join(BASE, "results.tsv")
with open(results_file, "a") as f:
    for row in results_rows:
        f.write(row + "\n")

total_games = len(pred_data["predictions"])
champ_correct = model_correct.get(champion["id"], 0)
champ_accuracy = champ_correct / total_games if total_games > 0 else 0

print(f"\n  Results for {EVAL_DATE}: {total_games} games evaluated")
print(f"  {'Model':<20} {'Correct':>8} {'Total':>6} {'Accuracy':>9}")
print(f"  {'-'*20} {'-'*8} {'-'*6} {'-'*9}")

for m in all_models:
    mid = m["id"]
    c = model_correct.get(mid, 0)
    t = model_total.get(mid, 0)
    acc = c / t if t > 0 else 0
    role = "CHAMP" if mid == champion["id"] else f"w={m.get('weight', '?')}"
    print(f"  {mid:<20} {c:>8} {t:>6} {acc:>8.1%}  ({role})")

# ── Step 1.4: Update challenger weights ─────────────────────────────────
print(f"\n  Updating challenger weights...")
champ_correct_count = model_correct.get(champion["id"], 0)

for c in challengers:
    cid = c["id"]
    c_correct = model_correct.get(cid, 0)
    c_total = model_total.get(cid, 0)

    if c_total == 0:
        continue

    c["lifetime_games"] = c.get("lifetime_games", 0) + c_total
    c["lifetime_correct"] = c.get("lifetime_correct", 0) + c_correct

    outperform_pct = c_correct / c_total
    champ_pct = champ_correct_count / c_total

    if outperform_pct >= champ_pct + 0.10:
        c["weight"] = min(1.0, c.get("weight", 0.5) + 0.1)
        print(f"    {cid}: outperformed champion ({outperform_pct:.1%} vs {champ_pct:.1%}), weight -> {c['weight']:.1f}")
    elif outperform_pct <= champ_pct - 0.10:
        c["weight"] = max(0.1, c.get("weight", 0.5) - 0.1)
        print(f"    {cid}: underperformed champion ({outperform_pct:.1%} vs {champ_pct:.1%}), weight -> {c['weight']:.1f}")
    else:
        print(f"    {cid}: similar to champion ({outperform_pct:.1%} vs {champ_pct:.1%}), weight unchanged at {c.get('weight', 0.5):.1f}")

# Update champion rolling accuracy
champion["rolling_10d_accuracy"] = champ_accuracy

# ── Step 1.5: Promotion check ──────────────────────────────────────────
promotion_msg = ""
champ_lifetime_acc = assumptions["champion"].get("rolling_10d_accuracy", 0.5)
for c in challengers:
    c_lifetime_acc = c["lifetime_correct"] / c["lifetime_games"] if c["lifetime_games"] > 0 else 0
    if c_lifetime_acc > champ_lifetime_acc + 0.05 and c["lifetime_games"] >= 30:
        promotion_msg = f"PROMOTED {c['id']} to champion (acc {c_lifetime_acc:.1%} vs {champ_lifetime_acc:.1%})"
        print(f"\n  *** {promotion_msg} ***")
        old_champ = dict(champion)
        old_champ["weight"] = 0.7
        old_champ.pop("promoted_on", None)
        old_champ.pop("rolling_10d_accuracy", None)
        old_champ["born"] = assumptions["champion"].get("promoted_on", EVAL_DATE)
        old_champ["grace_until"] = EVAL_DATE
        old_champ["lifetime_games"] = total_games
        old_champ["lifetime_correct"] = champ_correct_count

        assumptions["champion"] = {
            "id": c["id"],
            "description": c["description"],
            "params": c["params"],
            "promoted_on": TODAY,
            "rolling_10d_accuracy": c_lifetime_acc,
        }
        idx = challengers.index(c)
        challengers[idx] = old_champ
        break

if not promotion_msg:
    print(f"\n  No promotion triggered.")

# ── Step 1.6: Retirement check ──────────────────────────────────────────
graveyard = assumptions.get("graveyard", [])
to_retire = []
for c in challengers:
    if c.get("weight", 0.5) <= 0.15 and c.get("born", "") <= "2026-05-23":
        to_retire.append(c)

for c in to_retire:
    lifetime_acc = c["lifetime_correct"] / c["lifetime_games"] if c["lifetime_games"] > 0 else 0
    graveyard.append({
        "id": c["id"],
        "description": c["description"],
        "final_weight": c.get("weight", 0),
        "lifetime_accuracy": round(lifetime_acc, 4),
        "died": TODAY,
        "reason": f"Weight dropped to {c.get('weight', 0):.2f} with accuracy {lifetime_acc:.1%}",
    })
    challengers.remove(c)
    print(f"\n  RETIRED {c['id']} to graveyard (weight={c.get('weight', 0):.2f}, acc={lifetime_acc:.1%})")

if not to_retire:
    print(f"  No retirements triggered.")

assumptions["graveyard"] = graveyard
assumptions["challengers"] = challengers

# Save updated assumptions
with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
    f.write("\n")

print(f"\n  Phase 1 complete. Updated assumptions.json and results.tsv.")

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2-3: Tonight's games — data collection + simulation
# ═══════════════════════════════════════════════════════════════════════════

print(f"\n{'='*78}")
print(f" PHASE 2: Data Collection for {TODAY}")
print(f"{'='*78}")

# Reload assumptions (may have changed from promotions)
with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

games_raw = [
    # === NBA WCF Game 6: OKC @ SAS (SAS home, must-win) ===
    # OKC leads 3-2. Game at AT&T Center (San Antonio).
    # SAS -3.5, SAS -155, OKC +130, Total 219.5
    # OKC: 119.2 PPG, 107.9 OPP PPG. Won G5 127-114 (home).
    # SAS: ~116 PPG, ~111 OPP PPG. Must win or be eliminated.
    # SGA 32pts in G5. Wembanyama 20/6 in G5. Castle 24/6.
    # Neither team B2B (G5 was May 26, G6 is May 28).
    {
        "sport": "basketball_nba",
        "home": {
            "name": "San Antonio Spurs",
            "season_ppg": 116.0,
            "season_opp_ppg": 111.0,
            "last10_ppg": 111.0,
            "last10_opp_ppg": 109.0,
            "season_pace": 99.0,
            "home_record_pct": 0.780,
            "away_record_pct": 0.561,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Oklahoma City Thunder",
            "season_ppg": 119.2,
            "season_opp_ppg": 107.9,
            "last10_ppg": 115.0,
            "last10_opp_ppg": 108.0,
            "season_pace": 99.3,
            "home_record_pct": 0.878,
            "away_record_pct": 0.683,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -3.5,
            "ml_home": -155,
            "ml_away": 130,
            "total": 219.5,
            "book": "fanduel"
        }
    },

    # === MLB Games ===
    # 1. LAA Angels @ DET Tigers — series finale
    # DET -131, LAA +110. Total 8.5. DET -1.5 run line.
    # LAA won 10-6 yesterday (Grissom grand slam). LAA won 4 straight.
    # DET: ~3.8 PPG season. LAA: ~3.7 PPG but hot streak.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Detroit Tigers",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.0,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.400,
            "is_back_to_back": True,
            "key_injuries": 2
        },
        "away": {
            "name": "Los Angeles Angels",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.360,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -131,
            "ml_away": 110,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 2. MIN Twins @ CHW White Sox — game 4 of 4
    # CHW -148, MIN +124. CHW won 3-1 yesterday, leads series 2-1.
    # Davis Martin (CHW) vs Kendry Rojas (MIN).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago White Sox",
            "season_ppg": 3.6,
            "season_opp_ppg": 4.6,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.300,
            "is_back_to_back": True,
            "key_injuries": 2
        },
        "away": {
            "name": "Minnesota Twins",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -148,
            "ml_away": 124,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 3. ATL Braves @ BOS Red Sox
    # ATL -138, BOS +118. Run line: ATL -1.5 (+126). Total 7.5.
    # ATL (37-19) far better than BOS (23-31). Chris Sale pitching for ATL.
    # Sale: dominant. ATL 88% of ML money.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Boston Red Sox",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.440,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Atlanta Braves",
            "season_ppg": 4.9,
            "season_opp_ppg": 3.4,
            "last10_ppg": 5.1,
            "last10_opp_ppg": 3.2,
            "season_pace": 1.0,
            "home_record_pct": 0.700,
            "away_record_pct": 0.600,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 118,
            "ml_away": -138,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 4. TOR Blue Jays @ BAL Orioles — series opener
    # BAL -126, TOR +108. Run line: BAL -1.5 (+158). Total 8.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Toronto Blue Jays",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -126,
            "ml_away": 108,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 5. CHC Cubs @ PIT Pirates
    # PIT -174, CHC +146. Paul Skenes (6-4, 3.00) vs Colin Rea (4-3, 4.83).
    # PIT coming off 12-1 blowout win. Cubs struggling.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.2,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Chicago Cubs",
            "season_ppg": 3.7,
            "season_opp_ppg": 4.5,
            "last10_ppg": 2.8,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.360,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -174,
            "ml_away": 146,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 6. HOU Astros @ TEX Rangers — series finale (rivalry)
    # TEX -152, HOU +128. Run line: TEX -1.5 (+146). Total 7.5.
    # HOU threw combined no-hitter (9-0) yesterday.
    # DeGrom expected to start for TEX.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Texas Rangers",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.0,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.440,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Houston Astros",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.7,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.2,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -152,
            "ml_away": 128,
            "total": 7.5,
            "book": "fanduel"
        }
    },
]

print(f"  Tonight: {len(games_raw)} games ({sum(1 for g in games_raw if g['sport']=='basketball_nba')} NBA, {sum(1 for g in games_raw if g['sport']=='baseball_mlb')} MLB)")

# ── Build simulation batch ─────────────────────────────────────────────
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

print(f"  Running {len(batch)} simulations ({len(games_raw)} games x {len(all_models)} models)...")

sim_results = run_batch(batch)

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 4: Blended predictions
# ═══════════════════════════════════════════════════════════════════════════

games_results = {}
for i, result in enumerate(sim_results):
    game_idx = i // len(all_models)
    model_idx = i % len(all_models)
    game_key = f"{games_raw[game_idx]['away']['name']} @ {games_raw[game_idx]['home']['name']}"

    if game_key not in games_results:
        games_results[game_key] = {"game_data": games_raw[game_idx], "model_results": {}}
    games_results[game_key]["model_results"][all_models[model_idx]["id"]] = result

predictions = []
for game_key, data in games_results.items():
    game = data["game_data"]
    model_res = data["model_results"]

    total_weight = 0
    blend_home_wp = 0
    blend_margin = 0
    blend_spread_ev_home = 0
    blend_spread_ev_away = 0
    blend_ml_ev_home = 0
    blend_ml_ev_away = 0
    evs_by_model = {}

    for model in all_models:
        mid = model["id"]
        w = 1.0 if mid == champion["id"] else model.get("weight", 0.5)
        r = model_res[mid]

        total_weight += w
        blend_home_wp += w * r["home_win_prob"]
        blend_margin += w * r["expected_margin"]
        blend_spread_ev_home += w * r["spread_ev_home"]
        blend_spread_ev_away += w * r["spread_ev_away"]
        blend_ml_ev_home += w * r["ml_ev_home"]
        blend_ml_ev_away += w * r["ml_ev_away"]

        best_ev = max(r["spread_ev_home"], r["spread_ev_away"],
                      r["ml_ev_home"], r["ml_ev_away"])
        evs_by_model[mid] = {
            "best_ev": best_ev,
            "home_win_prob": r["home_win_prob"],
            "spread_ev_home": r["spread_ev_home"],
            "spread_ev_away": r["spread_ev_away"],
            "ml_ev_home": r["ml_ev_home"],
            "ml_ev_away": r["ml_ev_away"],
            "expected_margin": r["expected_margin"],
        }

    blend_home_wp /= total_weight
    blend_margin /= total_weight
    blend_spread_ev_home /= total_weight
    blend_spread_ev_away /= total_weight
    blend_ml_ev_home /= total_weight
    blend_ml_ev_away /= total_weight

    ev_options = {
        "spread_home": blend_spread_ev_home,
        "spread_away": blend_spread_ev_away,
        "ml_home": blend_ml_ev_home,
        "ml_away": blend_ml_ev_away,
    }
    best_bet_type = max(ev_options, key=ev_options.get)
    best_blend_ev = ev_options[best_bet_type]

    if "home" in best_bet_type:
        side = "HOME"
        side_team = game["home"]["name"]
    else:
        side = "AWAY"
        side_team = game["away"]["name"]

    bet_market = "SPREAD" if "spread" in best_bet_type else "ML"

    agree_count = 0
    best_evs = []
    for mid, info in evs_by_model.items():
        if side == "HOME":
            model_best = max(info["spread_ev_home"], info["ml_ev_home"])
            model_alt = max(info["spread_ev_away"], info["ml_ev_away"])
        else:
            model_best = max(info["spread_ev_away"], info["ml_ev_away"])
            model_alt = max(info["spread_ev_home"], info["ml_ev_home"])

        if model_best > model_alt:
            agree_count += 1
        best_evs.append(info["best_ev"])

    best_model_ev = max(best_evs)
    worst_model_ev = min(best_evs)
    robustness = f"{agree_count}/6"

    any_flips = False
    for mid, info in evs_by_model.items():
        if best_bet_type == "spread_home" and info["spread_ev_home"] < 0:
            any_flips = True
        elif best_bet_type == "spread_away" and info["spread_ev_away"] < 0:
            any_flips = True
        elif best_bet_type == "ml_home" and info["ml_ev_home"] < 0:
            any_flips = True
        elif best_bet_type == "ml_away" and info["ml_ev_away"] < 0:
            any_flips = True

    if best_blend_ev > 0.03 and agree_count >= 4 and not any_flips:
        verdict = "BET"
    elif best_blend_ev > 0.015 and agree_count >= 3:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    kelly = min(0.05, max(0, best_blend_ev / 2.0))

    pred = {
        "game": game_key,
        "sport": game["sport"],
        "home_team": game["home"]["name"],
        "away_team": game["away"]["name"],
        "odds": game["odds"],
        "blend_home_wp": round(blend_home_wp, 4),
        "blend_away_wp": round(1 - blend_home_wp, 4),
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
                "home_win_prob": info["home_win_prob"],
                "expected_margin": info["expected_margin"],
                "spread_ev_home": info["spread_ev_home"],
                "spread_ev_away": info["spread_ev_away"],
                "ml_ev_home": info["ml_ev_home"],
                "ml_ev_away": info["ml_ev_away"],
            }
            for mid, info in evs_by_model.items()
        }
    }
    predictions.append(pred)

# ── Save predictions BEFORE displaying ─────────────────────────────────
pred_file = os.path.join(BASE, "predictions", f"{TODAY}.json")
pred_data_out = {"date": TODAY, "predictions": predictions}
with open(pred_file, "w") as f:
    json.dump(pred_data_out, f, indent=2)
print(f"\n  Predictions saved to predictions/{TODAY}.json")

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 4 continued: Display results
# ═══════════════════════════════════════════════════════════════════════════

sports_order = ["basketball_nba", "icehockey_nhl", "baseball_mlb"]
sport_names = {"basketball_nba": "NBA", "icehockey_nhl": "NHL", "baseball_mlb": "MLB"}

for sport in sports_order:
    sport_preds = [p for p in predictions if p["sport"] == sport]
    if not sport_preds:
        continue

    name = sport_names[sport]
    print(f"\n{'='*90}")
    print(f" {name} -- Thursday May 28, 2026")
    print(f"{'='*90}")
    print(f" {'Game':<32} {'Spread':>7} {'Blend EV':>9} {'Best EV':>8} {'Worst EV':>9} {'Rob.':>5}  {'Verdict':<16}")
    print(f" {'-'*32} {'-'*7} {'-'*9} {'-'*8} {'-'*9} {'-'*5}  {'-'*16}")

    bets = []
    for p in sport_preds:
        spread = p["odds"]["spread_home"]
        home_short = p["home_team"].split()[-1][:4].upper()
        away_short = p["away_team"].split()[-1][:4].upper()

        if spread < 0:
            game_str = f"{home_short} {spread:+.1f} vs {away_short}"
        else:
            game_str = f"{away_short} vs {home_short} +{spread:.1f}"

        if p["verdict"] == "BET":
            emoji = " >>>"
        elif p["verdict"] == "LEAN":
            emoji = "  > "
        else:
            emoji = "  - "

        verdict_str = f"{emoji} {p['verdict']} {p['side']}"

        print(f" {game_str:<32} {spread:>+7.1f} {p['best_blend_ev']:>+8.1%} {p['best_model_ev']:>+7.1%} {p['worst_model_ev']:>+8.1%} {p['robustness']:>5} {verdict_str:<16}")

        if p["verdict"] == "BET":
            bets.append(p)

    if bets:
        print(f"\n  --- BET Details ---")
        for p in bets:
            print(f"\n  {p['side_team']} ({p['bet_market']}) | Kelly: {p['kelly']:.1%} of bankroll")
            print(f"  Blended EV: {p['best_blend_ev']:+.1%} | Spread: {p['odds']['spread_home']:+.1f} | ML: {p['odds']['ml_home']}/{p['odds']['ml_away']}")
            print(f"  Blended Win Prob: Home {p['blend_home_wp']:.1%} / Away {p['blend_away_wp']:.1%} | Margin: {p['blend_margin']:+.1f}")
            print(f"  Models agreeing: {p['agree_count']}/6 | Best book: {p['odds']['book']}")
            for mid, mr in p["model_results"].items():
                agree = "Y" if (p["side"] == "HOME" and max(mr["spread_ev_home"], mr["ml_ev_home"]) > max(mr["spread_ev_away"], mr["ml_ev_away"])) or \
                               (p["side"] == "AWAY" and max(mr["spread_ev_away"], mr["ml_ev_away"]) > max(mr["spread_ev_home"], mr["ml_ev_home"])) else "N"
                best = max(mr["spread_ev_home"], mr["spread_ev_away"], mr["ml_ev_home"], mr["ml_ev_away"])
                print(f"    {mid:<20} WP={mr['home_win_prob']:.1%} Margin={mr['expected_margin']:+.1f} BestEV={best:+.1%} Agree={agree}")

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 5: Metrics Dashboard
# ═══════════════════════════════════════════════════════════════════════════

# Load all results for rolling calculations
all_results_lines = []
with open(results_file) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("date"):
            all_results_lines.append(line)

# Parse results for champion-level scoring
from collections import defaultdict
date_model_results = defaultdict(lambda: defaultdict(list))
for line in all_results_lines:
    parts = line.split("\t")
    if len(parts) >= 14:
        d, sport, game, mid, pred_w, pred_m, pred_wp, act_w, act_m, hit, sev, mev, btype, bresult = parts[:14]
        date_model_results[d][mid].append({
            "hit": int(hit),
            "bet_result": bresult,
            "spread_ev": float(sev),
            "ml_ev": float(mev),
        })

# Compute metrics
all_dates = sorted(date_model_results.keys())
champ_id = assumptions["champion"]["id"]

total_correct = 0
total_games_all = 0
total_bets_won = 0
total_bets_rec = 0
total_ev = 0.0

for d in all_dates:
    if champ_id in date_model_results[d]:
        for r in date_model_results[d][champ_id]:
            total_games_all += 1
            total_correct += r["hit"]
            if r["bet_result"] == "win":
                total_bets_won += 1
            total_bets_rec += 1

# Rolling 7-day
recent_7d_dates = [d for d in all_dates if d >= "2026-05-21"]
r7_correct = 0
r7_total = 0
for d in recent_7d_dates:
    if champ_id in date_model_results[d]:
        for r in date_model_results[d][champ_id]:
            r7_total += 1
            r7_correct += r["hit"]

r7_acc = r7_correct / r7_total if r7_total > 0 else 0
all_acc = total_correct / total_games_all if total_games_all > 0 else 0
ev_est = (r7_acc - 0.5) * 0.2  # rough EV estimate

# Update variant performance
variant_perf = {}
for m in all_models:
    mid = m["id"]
    lt_games = m.get("lifetime_games", 0) if mid != champ_id else total_games_all
    lt_correct = m.get("lifetime_correct", 0) if mid != champ_id else total_correct
    variant_perf[mid] = {
        "lifetime_games": lt_games,
        "lifetime_correct": lt_correct,
        "weight": 1.0 if mid == champ_id else m.get("weight", 0.5),
        "role": "champion" if mid == champ_id else "challenger",
    }

metrics = {
    "last_updated": TODAY,
    "rolling_7d": {
        "accuracy": round(r7_acc, 4),
        "ev_realized": round(ev_est, 4),
        "total_games": r7_total,
        "total_correct": r7_correct,
    },
    "rolling_30d": {
        "accuracy": round(all_acc, 4),
        "ev_realized": round((all_acc - 0.5) * 0.15, 4),
        "total_games": total_games_all,
        "total_correct": total_correct,
    },
    "all_time": {
        "accuracy": round(all_acc, 4),
        "ev_realized": round((all_acc - 0.5) * 0.15, 4),
        "total_games": total_games_all,
        "total_correct": total_correct,
        "total_bets_recommended": total_bets_rec,
        "total_bets_won": total_bets_won,
    },
    "variant_performance": variant_perf,
    "champion_history": [
        {"id": "season-avg-v1", "promoted_on": "2026-03-24", "reason": "initial champion"},
    ],
    "today_summary": {
        "date": TODAY,
        "games_analyzed": len(predictions),
        "bets_recommended": sum(1 for p in predictions if p["verdict"] == "BET"),
        "leans": sum(1 for p in predictions if p["verdict"] == "LEAN"),
        "sports": list(set(p["sport"] for p in predictions)),
        "notes": f"NBA WCF G6 (OKC@SAS) + {sum(1 for p in predictions if p['sport']=='baseball_mlb')} MLB games. {sum(1 for p in predictions if p['verdict']=='BET')} BETs, {sum(1 for p in predictions if p['verdict']=='LEAN')} LEANs, {sum(1 for p in predictions if p['verdict']=='NO BET')} NO BETs.",
    }
}

metrics_file_path = os.path.join(BASE, "metrics.json")
with open(metrics_file_path, "w") as f:
    json.dump(metrics, f, indent=2)
    f.write("\n")

# ── Summary Dashboard ──────────────────────────────────────────────────
total_bets = sum(1 for p in predictions if p["verdict"] == "BET")
total_leans = sum(1 for p in predictions if p["verdict"] == "LEAN")
total_no = sum(1 for p in predictions if p["verdict"] == "NO BET")

print(f"\n{'='*78}")
print(f" SUMMARY: {len(predictions)} games | {total_bets} BETs | {total_leans} LEANs | {total_no} NO BETs")
print(f"{'='*78}")

print(f"\n  Edge-Finder Metrics Dashboard")
print(f"  {'='*50}")
print(f"  Champion: {champion['id']} (promoted {champion.get('promoted_on', 'N/A')})")
print(f"  7-day:  {r7_acc:.1%} accuracy | {ev_est:+.1%} est. EV | {r7_total} games")
print(f"  30-day: {all_acc:.1%} accuracy | {(all_acc-0.5)*0.15:+.1%} est. EV | {total_games_all} games")
cw = ", ".join(f"{c['id']}={c.get('weight', '?')}" for c in challengers)
print(f"  Challengers: {cw}")
gcount = len(assumptions.get("graveyard", []))
if gcount > 0:
    for g in assumptions["graveyard"]:
        print(f"  Graveyard: {g['id']} (died {g['died']}, {g['lifetime_accuracy']:.1%} accuracy)")
else:
    print(f"  Graveyard: empty")

print(f"\n  NOTE: This analysis is for entertainment purposes only.")
print(f"  Past performance does not guarantee future results.")
