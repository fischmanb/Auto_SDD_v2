#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-05-21.
Compiles gathered odds/stats, runs sims, computes blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch, SimResult

TODAY = "2026-05-21"

# ── Assumption models from assumptions.json ─────────────────────────────
with open(os.path.join(os.path.dirname(__file__), "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

# ── Games data ──────────────────────────────────────────────────────────
# NBA ECF Game 2: Cleveland Cavaliers @ New York Knicks
# NHL ECF Game 1: Montreal Canadiens @ Carolina Hurricanes
# MLB: 6 games

games_raw = [
    # === NBA ===
    # ECF Game 2: Cavaliers @ Knicks. NYK leads 1-0.
    # NYK: 53-29, 116.5 PPG, 110.1 OPP PPG. CLE: 52-30, 119.0 PPG, 115.0 OPP PPG.
    # Both teams fully healthy. Game 1 was May 19 (not B2B).
    # NYK last 5 playoff: 122.4 PPG, 102.4 OPP. CLE last 5 playoff: 110.4 PPG, 108.0 OPP.
    {
        "sport": "basketball_nba",
        "home": {
            "name": "New York Knicks",
            "season_ppg": 116.5,
            "season_opp_ppg": 110.1,
            "last10_ppg": 122.4,
            "last10_opp_ppg": 102.4,
            "season_pace": 99.8,
            "home_record_pct": 0.756,
            "away_record_pct": 0.537,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Cleveland Cavaliers",
            "season_ppg": 119.0,
            "season_opp_ppg": 115.0,
            "last10_ppg": 110.4,
            "last10_opp_ppg": 108.0,
            "season_pace": 99.5,
            "home_record_pct": 0.707,
            "away_record_pct": 0.561,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -6.5,
            "ml_home": -225,
            "ml_away": 185,
            "total": 214.5,
            "book": "fanduel"
        }
    },
    # === NHL ===
    # ECF Game 1: Canadiens @ Hurricanes. CAR 8-0 in playoffs (swept PHI).
    # CAR: 53-22-7, estimated 3.4 GPG, 2.5 OPP GPG. MTL: 48-24-10, ~3.0 GPG, 2.8 OPP GPG.
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Carolina Hurricanes",
            "season_ppg": 3.4,
            "season_opp_ppg": 2.5,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 2.1,
            "season_pace": 1.0,
            "home_record_pct": 0.720,
            "away_record_pct": 0.580,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Montreal Canadiens",
            "season_ppg": 3.0,
            "season_opp_ppg": 2.8,
            "last10_ppg": 3.1,
            "last10_opp_ppg": 2.6,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -205,
            "ml_away": 170,
            "total": 5.5,
            "book": "betmgm"
        }
    },
    # === MLB ===
    # CLE Guardians (29-22) @ DET Tigers (20-30)
    # Joey Cantillo vs Casey Mize. DET missing 3 starters, 2-13 last 15.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Detroit Tigers",
            "season_ppg": 3.6,
            "season_opp_ppg": 4.4,
            "last10_ppg": 2.5,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.300,
            "is_back_to_back": False,
            "key_injuries": 3
        },
        "away": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.7,
            "last10_ppg": 5.1,
            "last10_opp_ppg": 3.3,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -115,
            "ml_away": 100,
            "total": 8.0,
            "book": "draftkings"
        }
    },
    # PIT Pirates (25-24) @ STL Cardinals (28-20)
    # Braxton Ashcraft vs Dustin May
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.3,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 104,
            "ml_away": -126,
            "total": 8.5,
            "book": "consensus"
        }
    },
    # NYM Mets (21-28) @ WSH Nationals (25-25)
    # David Peterson vs Cade Cavalli
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Washington Nationals",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "New York Mets",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.5,
            "last10_ppg": 3.7,
            "last10_opp_ppg": 4.7,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.360,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -105,
            "ml_away": -115,
            "total": 8.0,
            "book": "consensus"
        }
    },
    # ATL Braves (34-16) @ MIA Marlins (22-28)
    # Spencer Strider vs Sandy Alcantara
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Miami Marlins",
            "season_ppg": 3.6,
            "season_opp_ppg": 4.6,
            "last10_ppg": 3.4,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.340,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Atlanta Braves",
            "season_ppg": 5.0,
            "season_opp_ppg": 3.3,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.1,
            "season_pace": 1.0,
            "home_record_pct": 0.700,
            "away_record_pct": 0.600,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 119,
            "ml_away": -143,
            "total": 7.5,
            "book": "consensus"
        }
    },
    # TOR Blue Jays (22-27) @ NYY Yankees (30-20)
    # Braydon Fisher vs Carlos Rodon
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Yankees",
            "season_ppg": 4.8,
            "season_opp_ppg": 4.0,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Toronto Blue Jays",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.4,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -171,
            "ml_away": 141,
            "total": 8.5,
            "book": "fanduel"
        }
    },
    # OAK Athletics @ LAA Angels
    # Luis Severino vs Jose Soriano. Pick'em game.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Angels",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.5,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.7,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.340,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Sacramento Athletics",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -108,
            "ml_away": -108,
            "total": 8.0,
            "book": "consensus"
        }
    },
]

# ── Build batch ─────────────────────────────────────────────────────────
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

print(f"Running {len(batch)} simulations ({len(games_raw)} games x {len(all_models)} models)...")

# ── Run simulation ──────────────────────────────────────────────────────
results = run_batch(batch)

# ── Organize results by game ────────────────────────────────────────────
games_results = {}
for i, result in enumerate(results):
    game_idx = i // len(all_models)
    model_idx = i % len(all_models)
    game_key = f"{games_raw[game_idx]['away']['name']} @ {games_raw[game_idx]['home']['name']}"

    if game_key not in games_results:
        games_results[game_key] = {
            "game_data": games_raw[game_idx],
            "model_results": {}
        }
    games_results[game_key]["model_results"][all_models[model_idx]["id"]] = result

# ── Compute blended predictions ─────────────────────────────────────────
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
    worst_evs = []
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
        worst_evs.append(min(info["spread_ev_home"], info["spread_ev_away"],
                             info["ml_ev_home"], info["ml_ev_away"]))

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

# ── Save predictions ────────────────────────────────────────────────────
pred_file = os.path.join(os.path.dirname(__file__), "predictions", f"{TODAY}.json")
pred_data = {"date": TODAY, "predictions": predictions}
with open(pred_file, "w") as f:
    json.dump(pred_data, f, indent=2)
print(f"\nPredictions saved to predictions/{TODAY}.json")

# ── Display results ─────────────────────────────────────────────────────
sports_order = ["basketball_nba", "icehockey_nhl", "baseball_mlb"]
sport_names = {"basketball_nba": "NBA", "icehockey_nhl": "NHL", "baseball_mlb": "MLB"}

for sport in sports_order:
    sport_preds = [p for p in predictions if p["sport"] == sport]
    if not sport_preds:
        continue

    name = sport_names[sport]
    print(f"\n{'='*78}")
    print(f" {name} -- Wednesday May 21, 2026")
    print(f"{'='*78}")
    print(f"{'Game':<30} {'Spread':>7} {'Blend EV':>9} {'Best EV':>8} {'Worst EV':>9} {'Rob.':>5} {'Verdict':<16}")
    print(f"{'-'*30} {'-'*7} {'-'*9} {'-'*8} {'-'*9} {'-'*5} {'-'*16}")

    bets = []
    for p in sport_preds:
        spread = p["odds"]["spread_home"]
        home_abbr = p["home_team"].split()[-1][:3].upper()
        away_abbr = p["away_team"].split()[-1][:3].upper()

        if spread < 0:
            game_str = f"{home_abbr} {spread} vs {away_abbr}"
        else:
            game_str = f"{away_abbr} {-spread} @ {home_abbr}"

        if p["verdict"] == "BET":
            icon = "BET"
            emoji = ">>>"
        elif p["verdict"] == "LEAN":
            icon = "LEAN"
            emoji = " > "
        else:
            icon = "NO BET"
            emoji = " - "

        verdict_str = f"{emoji} {icon} {p['side']}"

        print(f"{game_str:<30} {spread:>+7.1f} {p['best_blend_ev']:>+8.1%} {p['best_model_ev']:>+7.1%} {p['worst_model_ev']:>+8.1%} {p['robustness']:>5} {verdict_str:<16}")

        if p["verdict"] == "BET":
            bets.append(p)

    if bets:
        print(f"\n  --- BET Details ---")
        for p in bets:
            print(f"\n  {p['side_team']} ({p['bet_market']}) | Kelly: {p['kelly']:.1%} of bankroll")
            print(f"  Blended EV: {p['best_blend_ev']:+.1%} | Spread: {p['odds']['spread_home']:+.1f} | ML: {p['odds']['ml_home']}/{p['odds']['ml_away']}")
            print(f"  Models agreeing: {p['agree_count']}/6 | Best book: {p['odds']['book']}")
            for mid, mr in p["model_results"].items():
                agree = "Y" if (p["side"] == "HOME" and max(mr["spread_ev_home"], mr["ml_ev_home"]) > max(mr["spread_ev_away"], mr["ml_ev_away"])) or \
                               (p["side"] == "AWAY" and max(mr["spread_ev_away"], mr["ml_ev_away"]) > max(mr["spread_ev_home"], mr["ml_ev_home"])) else "N"
                best = max(mr["spread_ev_home"], mr["spread_ev_away"], mr["ml_ev_home"], mr["ml_ev_away"])
                print(f"    {mid:<20} WP={mr['home_win_prob']:.1%} Margin={mr['expected_margin']:+.1f} BestEV={best:+.1%} Agree={agree}")

# ── Summary stats ───────────────────────────────────────────────────────
total_bets = sum(1 for p in predictions if p["verdict"] == "BET")
total_leans = sum(1 for p in predictions if p["verdict"] == "LEAN")
total_no = sum(1 for p in predictions if p["verdict"] == "NO BET")

print(f"\n{'='*78}")
print(f" SUMMARY: {len(predictions)} games analyzed | {total_bets} BETs | {total_leans} LEANs | {total_no} NO BETs")
print(f"{'='*78}")

# ── Update metrics.json ─────────────────────────────────────────────────
metrics_file = os.path.join(os.path.dirname(__file__), "metrics.json")
with open(metrics_file) as f:
    metrics = json.load(f)

metrics["last_updated"] = TODAY
metrics["all_time"]["total_bets_recommended"] = metrics["all_time"].get("total_bets_recommended", 0) + total_bets
metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": total_bets,
    "leans": total_leans,
    "sports": list(set(p["sport"] for p in predictions)),
    "notes": f"NBA ECF Gm2 (CLE@NYK) + NHL ECF Gm1 (MTL@CAR) + {sum(1 for p in predictions if p['sport']=='baseball_mlb')} MLB games. {total_bets} BETs, {total_leans} LEANs."
}

for model in all_models:
    mid = model["id"]
    if mid not in metrics["variant_performance"]:
        metrics["variant_performance"][mid] = {
            "lifetime_games": 0,
            "lifetime_correct": 0,
            "weight": model.get("weight", 1.0),
            "role": "champion" if mid == champion["id"] else "challenger"
        }
    metrics["variant_performance"][mid]["weight"] = model.get("weight", 1.0) if mid != champion["id"] else 1.0

with open(metrics_file, "w") as f:
    json.dump(metrics, f, indent=2)

print(f"\nMetrics updated in metrics.json")

print(f"\n  Edge-Finder Metrics")
print(f"  {'='*40}")
print(f"  Champion: {champion['id']} (promoted {champion['promoted_on']})")
print(f"  7-day:  {metrics['rolling_7d']['accuracy'] or 'N/A'} accuracy | {metrics['rolling_7d']['ev_realized'] or 'N/A'} realized EV | {metrics['rolling_7d']['total_games']} games")
print(f"  30-day: {metrics['rolling_30d']['accuracy'] or 'N/A'} accuracy | {metrics['rolling_30d']['ev_realized'] or 'N/A'} realized EV | {metrics['rolling_30d']['total_games']} games")
cw = ", ".join(f"{c['id']}={c['weight']}" for c in challengers)
print(f"  Challengers: {cw}")
gcount = len(assumptions.get("graveyard", []))
print(f"  Graveyard: {gcount} retired variants")

print(f"\n  NOTE: This analysis is for entertainment purposes only.")
print(f"  Past performance does not guarantee future results.")
