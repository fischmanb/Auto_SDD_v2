#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-05-23.
Compiles gathered odds/stats, runs sims, computes blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch, SimResult

TODAY = "2026-05-23"

# ── Assumption models from assumptions.json ─────────────────────────────
with open(os.path.join(os.path.dirname(__file__), "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

# ── Games data ──────────────────────────────────────────────────────────
# NBA ECF Game 3: New York Knicks @ Cleveland Cavaliers (NYK leads 2-0)
# NHL ECF Game 2: Montreal Canadiens @ Carolina Hurricanes (MTL leads 1-0)
# MLB: 13 games (TB@NYY postponed, DET@BAL postponed)

games_raw = [
    # === NBA ===
    # ECF Game 3: Knicks @ Cavaliers. NYK leads 2-0.
    # CLE: 52-30, 119.0 PPG, 115.0 OPP. Playoff last 5: ~108 PPG, 112 OPP (struggling).
    # NYK: 53-29, 116.5 PPG, 110.1 OPP. Playoff last 5: 119.2 PPG, 105.6 OPP (dominant).
    # CLE is desperate at home. Jalen Brunson status questionable (knee soreness).
    # Key: CLE hasn't lost at home this postseason until now. Must-win.
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Cleveland Cavaliers",
            "season_ppg": 119.0,
            "season_opp_ppg": 115.0,
            "last10_ppg": 108.0,
            "last10_opp_ppg": 112.0,
            "season_pace": 99.5,
            "home_record_pct": 0.707,
            "away_record_pct": 0.561,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "New York Knicks",
            "season_ppg": 116.5,
            "season_opp_ppg": 110.1,
            "last10_ppg": 119.2,
            "last10_opp_ppg": 105.6,
            "season_pace": 99.8,
            "home_record_pct": 0.756,
            "away_record_pct": 0.537,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -2.5,
            "ml_home": -126,
            "ml_away": 108,
            "total": 213.5,
            "book": "fanduel"
        }
    },
    # === NHL ===
    # ECF Game 2: Canadiens @ Hurricanes. MTL stole Game 1 (6-2).
    # CAR: 53-22-7, 3.4 GPG, 2.5 OPP. Playoff: 3.6 GPG, 2.1 OPP (dominant until G1 loss).
    # MTL: 48-24-10, 3.0 GPG, 2.8 OPP. Playoff: 3.3 GPG, 2.4 OPP (riding momentum).
    # CAR expected to bounce back hard at home after embarrassing G1 loss.
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Carolina Hurricanes",
            "season_ppg": 3.4,
            "season_opp_ppg": 2.5,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 2.3,
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
            "last10_ppg": 3.3,
            "last10_opp_ppg": 2.4,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -207,
            "ml_away": 171,
            "total": 5.5,
            "book": "fanduel"
        }
    },
    # === MLB ===
    # STL Cardinals @ CIN Reds (DH Game 1 - yesterday PPD)
    # CIN: 24-25, ~4.4 RPG, 4.2 OPP. Last 10: 4.6 RPG, 3.9 OPP. Home: .520
    # STL: 28-20, ~4.3 RPG, 3.8 OPP. Last 10: 4.1 RPG, 4.0 OPP. Away: .500
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.3,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -125,
            "ml_away": 105,
            "total": 9.5,
            "book": "consensus"
        }
    },
    # HOU Astros @ CHC Cubs
    # CHC: 22-27, ~4.0 RPG, 4.5 OPP. On 6-game losing streak.
    # HOU: 26-23, ~4.2 RPG, 3.9 OPP. Last 10: 4.5 RPG, 3.5 OPP. Road: .520
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago Cubs",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.5,
            "last10_ppg": 3.4,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Houston Astros",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -142,
            "ml_away": 120,
            "total": 8.5,
            "book": "consensus"
        }
    },
    # LAD Dodgers @ MIL Brewers
    # MIL: 30-18, ~4.6 RPG, 3.5 OPP. On 5-game win streak. Home: .600
    # LAD: 32-17, ~5.1 RPG, 3.8 OPP. Last 10: 4.5 RPG, 4.2 OPP. Sasaki pitching.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.5,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.2,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.560,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.1,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.700,
            "away_record_pct": 0.560,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 108,
            "ml_away": -126,
            "total": 9.0,
            "book": "fanduel"
        }
    },
    # WAS Nationals @ ATL Braves
    # ATL: 35-16, ~5.1 RPG, 3.4 OPP. 4-game win streak. Home: .700
    # WAS: 25-26, ~4.0 RPG, 4.3 OPP. Road: .440
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Atlanta Braves",
            "season_ppg": 5.1,
            "season_opp_ppg": 3.4,
            "last10_ppg": 5.4,
            "last10_opp_ppg": 3.2,
            "season_pace": 1.0,
            "home_record_pct": 0.700,
            "away_record_pct": 0.620,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Washington Nationals",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -178,
            "ml_away": 150,
            "total": 8.0,
            "book": "draftkings"
        }
    },
    # NYM Mets @ MIA Marlins
    # MIA: 22-29, ~3.6 RPG, 4.5 OPP. Won yesterday 2-1. Max Meyer pitching (2.85 ERA).
    # NYM: 21-29, ~3.9 RPG, 4.4 OPP. Lost yesterday. Freddy Peralta pitching (3.31 ERA).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Miami Marlins",
            "season_ppg": 3.6,
            "season_opp_ppg": 4.5,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.320,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "New York Mets",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.4,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.360,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -115,
            "ml_away": -105,
            "total": 8.0,
            "book": "consensus"
        }
    },
    # SEA Mariners @ KC Royals
    # SEA: 30-19, ~4.1 RPG, 3.2 OPP. Won yesterday 2-0. Road: .560
    # KC: 22-28, ~3.8 RPG, 4.3 OPP. Home: .440
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Kansas City Royals",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Seattle Mariners",
            "season_ppg": 4.1,
            "season_opp_ppg": 3.2,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.0,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.560,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 110,
            "ml_away": -142,
            "total": 7.5,
            "book": "fanduel"
        }
    },
    # PIT Pirates @ TOR Blue Jays
    # PIT: 26-25, ~4.1 RPG, 4.0 OPP. Away: .480
    # TOR: 24-27, ~3.8 RPG, 4.3 OPP. Home: .480
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Toronto Blue Jays",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.400,
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
            "home_record_pct": 0.540,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 128,
            "ml_away": -152,
            "total": 7.5,
            "book": "fanduel"
        }
    },
    # CLE Guardians @ PHI Phillies
    # PHI: 31-19, ~4.8 RPG, 3.6 OPP. Home: .640
    # CLE: 29-22, ~4.6 RPG, 3.7 OPP. Away: .500
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.8,
            "season_opp_ppg": 3.6,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.4,
            "season_pace": 1.0,
            "home_record_pct": 0.640,
            "away_record_pct": 0.560,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -175,
            "ml_away": 148,
            "total": 8.0,
            "book": "consensus"
        }
    },
    # MIN Twins @ BOS Red Sox
    # BOS: 28-22, ~4.5 RPG, 4.0 OPP. Home: .560
    # MIN: 26-24, ~4.3 RPG, 4.1 OPP. Away: .480
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Boston Red Sox",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Minnesota Twins",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -112,
            "ml_away": -104,
            "total": 8.5,
            "book": "consensus"
        }
    },
    # CWS White Sox @ SF Giants
    # SF: 25-25, ~3.9 RPG, 3.8 OPP. Home: .520
    # CWS: 14-37, ~3.2 RPG, 5.1 OPP. Worst team in MLB. Away: .260
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Francisco Giants",
            "season_ppg": 3.9,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Chicago White Sox",
            "season_ppg": 3.2,
            "season_opp_ppg": 5.1,
            "last10_ppg": 3.0,
            "last10_opp_ppg": 5.3,
            "season_pace": 1.0,
            "home_record_pct": 0.320,
            "away_record_pct": 0.260,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -170,
            "ml_away": 145,
            "total": 7.5,
            "book": "consensus"
        }
    },
    # TEX Rangers @ LAA Angels
    # LAA: 18-34, ~3.7 RPG, 4.8 OPP. Home: .380
    # TEX: 24-26, ~4.1 RPG, 4.3 OPP. Away: .440
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Angels",
            "season_ppg": 3.7,
            "season_opp_ppg": 4.8,
            "last10_ppg": 3.4,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.380,
            "away_record_pct": 0.300,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Texas Rangers",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 116,
            "ml_away": -136,
            "total": 8.0,
            "book": "fanduel"
        }
    },
    # SAC Athletics @ SD Padres
    # SD: 29-22, ~4.5 RPG, 3.7 OPP. Home: .600
    # SAC: 23-28, ~4.0 RPG, 4.2 OPP. Away: .400
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Diego Padres",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Sacramento Athletics",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -175,
            "ml_away": 148,
            "total": 8.0,
            "book": "consensus"
        }
    },
    # COL Rockies @ ARI Diamondbacks
    # ARI: 27-24, ~4.4 RPG, 4.0 OPP. Home: .560
    # COL: 18-33, ~3.8 RPG, 5.0 OPP. Road: .280 (worst road team in MLB)
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Colorado Rockies",
            "season_ppg": 3.8,
            "season_opp_ppg": 5.0,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 5.3,
            "season_pace": 1.0,
            "home_record_pct": 0.420,
            "away_record_pct": 0.280,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -185,
            "ml_away": 155,
            "total": 9.0,
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
        "spread_ev_home": blend_spread_ev_home,
        "spread_ev_away": blend_spread_ev_away,
        "ml_ev_home": blend_ml_ev_home,
        "ml_ev_away": blend_ml_ev_away,
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
        if best_bet_type == "spread_ev_home" and info["spread_ev_home"] < 0:
            any_flips = True
        elif best_bet_type == "spread_ev_away" and info["spread_ev_away"] < 0:
            any_flips = True
        elif best_bet_type == "ml_ev_home" and info["ml_ev_home"] < 0:
            any_flips = True
        elif best_bet_type == "ml_ev_away" and info["ml_ev_away"] < 0:
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
    print(f" {name} -- Saturday May 23, 2026")
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
