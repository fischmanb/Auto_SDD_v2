#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-05-26.
Compiles gathered odds/stats, runs sims, computes blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch, SimResult

TODAY = "2026-05-26"

with open(os.path.join(os.path.dirname(__file__), "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

games_raw = [
    # === NBA WCF Game 5: Spurs @ Thunder ===
    # Series tied 2-2. OKC 64-18 reg season (#1 seed). SAS ~55-27 (#2 seed).
    # OKC: 119.2 PPG, 107.9 OPP PPG, Pace 99.3. Won G2 (122-113), G3 (123-108).
    # SAS: ~116 PPG, ~111 OPP PPG. Won G1 OT (122-115), G4 (103-82).
    # Wembanyama 25.0/11.5/3.1, DPOY. Fox 18.6, Castle 16.7.
    # SGA leading OKC. Neither team B2B (Game 4 was May 24).
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Oklahoma City Thunder",
            "season_ppg": 119.2,
            "season_opp_ppg": 107.9,
            "last10_ppg": 112.5,
            "last10_opp_ppg": 105.8,
            "season_pace": 99.3,
            "home_record_pct": 0.878,
            "away_record_pct": 0.683,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "San Antonio Spurs",
            "season_ppg": 116.0,
            "season_opp_ppg": 111.0,
            "last10_ppg": 112.5,
            "last10_opp_ppg": 108.0,
            "season_pace": 99.0,
            "home_record_pct": 0.780,
            "away_record_pct": 0.561,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -5.5,
            "ml_home": -190,
            "ml_away": 160,
            "total": 216.5,
            "book": "fanduel"
        }
    },
    # === NHL WCF Game 4: Avalanche @ Golden Knights ===
    # VGK leads 3-0 (potential sweep). Game at T-Mobile Arena.
    # COL slight ML favorite (-115) despite being down 3-0.
    # COL: ~3.4 GPG, 2.6 OPP GPG. VGK: ~3.2 GPG, 2.7 OPP GPG.
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Vegas Golden Knights",
            "season_ppg": 3.2,
            "season_opp_ppg": 2.7,
            "last10_ppg": 3.0,
            "last10_opp_ppg": 2.5,
            "season_pace": 1.0,
            "home_record_pct": 0.680,
            "away_record_pct": 0.580,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Colorado Avalanche",
            "season_ppg": 3.4,
            "season_opp_ppg": 2.6,
            "last10_ppg": 3.2,
            "last10_opp_ppg": 2.8,
            "season_pace": 1.0,
            "home_record_pct": 0.700,
            "away_record_pct": 0.600,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -105,
            "ml_away": -115,
            "total": 6.0,
            "book": "fanduel"
        }
    },
    # === MLB ===
    # 1. WSH Nationals @ CLE Guardians — Both B2B
    # CLE: 32-19, Cantillo (4-1). WSH: 26-26, Cavalli (2-3).
    # CLE -138, WSH +118
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Washington Nationals",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.2,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -138,
            "ml_away": 118,
            "total": 7.5,
            "book": "fanduel"
        }
    },
    # 2. TB Rays @ BAL Orioles — Both B2B
    # TB: 28-24. BAL: 26-24. Pick'em. Jax (1-2) vs Baz (1-5).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.500,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.1,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -108,
            "ml_away": -108,
            "total": 8.5,
            "book": "fanduel"
        }
    },
    # 3. LAA Angels @ DET Tigers — Neither B2B
    # DET -132, LAA +112. Montero vs Kochanowicz.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Detroit Tigers",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.0,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Los Angeles Angels",
            "season_ppg": 3.7,
            "season_opp_ppg": 4.4,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.340,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -132,
            "ml_away": 112,
            "total": 7.5,
            "book": "fanduel"
        }
    },
    # 4. CHC Cubs @ PIT Pirates — Both B2B
    # PIT -126, CHC +108. Cubs on 9-game losing streak.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.1,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Chicago Cubs",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.4,
            "last10_ppg": 3.0,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.380,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -126,
            "ml_away": 108,
            "total": 8.0,
            "book": "fanduel"
        }
    },
    # 5. ATL Braves @ BOS Red Sox — Neither B2B
    # Pick'em: ATL -108, BOS -108. O/U 8.0.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Boston Red Sox",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Atlanta Braves",
            "season_ppg": 4.8,
            "season_opp_ppg": 3.5,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.3,
            "season_pace": 1.0,
            "home_record_pct": 0.680,
            "away_record_pct": 0.580,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -108,
            "ml_away": -108,
            "total": 8.0,
            "book": "fanduel"
        }
    },
    # 6. MIA Marlins @ TOR Blue Jays — Neither B2B
    # TOR -142, MIA +120.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Toronto Blue Jays",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Miami Marlins",
            "season_ppg": 3.5,
            "season_opp_ppg": 4.7,
            "last10_ppg": 3.3,
            "last10_opp_ppg": 4.9,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.320,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -142,
            "ml_away": 120,
            "total": 7.5,
            "book": "fanduel"
        }
    },
    # 7. CIN Reds @ NYM Mets — Both B2B
    # CIN -116, NYM -102. Burns (6-1, 1.83 ERA) vs Peterson (5.03 ERA).
    # Reds won 7-2 yesterday. Mets on 4-game losing streak (now 5).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Mets",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.5,
            "last10_ppg": 3.2,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.360,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.4,
            "season_opp_ppg": 3.9,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -102,
            "ml_away": -116,
            "total": 8.5,
            "book": "fanduel"
        }
    },
    # 8. MIN Twins @ CWS White Sox — Both B2B
    # MIN -115, CWS -105. CWS won 3-1 yesterday.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago White Sox",
            "season_ppg": 3.5,
            "season_opp_ppg": 4.7,
            "last10_ppg": 3.3,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.380,
            "away_record_pct": 0.300,
            "is_back_to_back": True,
            "key_injuries": 2
        },
        "away": {
            "name": "Minnesota Twins",
            "season_ppg": 4.3,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -105,
            "ml_away": -115,
            "total": 8.0,
            "book": "fanduel"
        }
    },
    # 9. NYY Yankees @ KC Royals — Both B2B
    # NYY -205, KC +172. NYY 12-game series win streak vs KC.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Kansas City Royals",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.420,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "New York Yankees",
            "season_ppg": 4.9,
            "season_opp_ppg": 3.8,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.560,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 172,
            "ml_away": -205,
            "total": 8.5,
            "book": "fanduel"
        }
    },
    # 10. STL Cardinals @ MIL Brewers — Both B2B
    # MIL favored. STL +146. Misiorowski had 12K no-hit bid yesterday.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.440,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -172,
            "ml_away": 146,
            "total": 8.5,
            "book": "fanduel"
        }
    },
    # 11. HOU Astros @ TEX Rangers — Both B2B
    # TEX -134, HOU +114. HOU threw combined no-hitter (9-0) yesterday.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Texas Rangers",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.1,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.440,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Houston Astros",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.8,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.4,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -134,
            "ml_away": 114,
            "total": 8.0,
            "book": "fanduel"
        }
    },
    # 12. SEA Mariners @ SAC Athletics — Both B2B
    # SEA -118, SAC +100. SEA won 9-2 yesterday.
    # Hancock (3-2, 3.07) vs Severino (2-5, 4.23).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Sacramento Athletics",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.420,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Seattle Mariners",
            "season_ppg": 4.1,
            "season_opp_ppg": 3.6,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.3,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.500,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 100,
            "ml_away": -118,
            "total": 7.5,
            "book": "fanduel"
        }
    },
    # 13. PHI Phillies @ SD Padres — Both B2B
    # SD -120, PHI +102. PHI won 3-0 yesterday (Schwarber HR #21).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Diego Padres",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.6,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.3,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -120,
            "ml_away": 102,
            "total": 8.5,
            "book": "fanduel"
        }
    },
    # 14. ARI Diamondbacks @ SF Giants — Neither B2B
    # Pick'em: ARI -108, SF -108.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Francisco Giants",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.1,
            "last10_ppg": 3.7,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.420,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -108,
            "ml_away": -108,
            "total": 8.0,
            "book": "fanduel"
        }
    },
    # 15. COL Rockies @ LAD Dodgers — Both B2B
    # LAD -235, COL +194. LAD won 5-3 yesterday.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.0,
            "season_opp_ppg": 3.5,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.2,
            "season_pace": 1.0,
            "home_record_pct": 0.680,
            "away_record_pct": 0.580,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Colorado Rockies",
            "season_ppg": 3.6,
            "season_opp_ppg": 5.0,
            "last10_ppg": 3.4,
            "last10_opp_ppg": 5.2,
            "season_pace": 1.0,
            "home_record_pct": 0.360,
            "away_record_pct": 0.260,
            "is_back_to_back": True,
            "key_injuries": 2
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -235,
            "ml_away": 194,
            "total": 9.0,
            "book": "fanduel"
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
    print(f" {name} -- Tuesday May 26, 2026")
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
            emoji = ">>>"
        elif p["verdict"] == "LEAN":
            emoji = " > "
        else:
            emoji = " - "

        verdict_str = f"{emoji} {p['verdict']} {p['side']}"

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

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": total_bets,
    "leans": total_leans,
    "sports": list(set(p["sport"] for p in predictions)),
    "notes": f"NBA WCF G5 (SAS@OKC) + NHL WCF G4 (COL@VGK) + {sum(1 for p in predictions if p['sport']=='baseball_mlb')} MLB games. {total_bets} BETs, {total_leans} LEANs, {total_no} NO BETs."
}

with open(metrics_file, "w") as f:
    json.dump(metrics, f, indent=2)

print(f"\n  Edge-Finder Metrics")
print(f"  {'='*40}")
print(f"  Champion: {champion['id']} (promoted {champion['promoted_on']})")
print(f"  7-day:  {metrics['rolling_7d']['accuracy']:.1%} accuracy | {metrics['rolling_7d']['ev_realized']:+.1%} realized EV | {metrics['rolling_7d']['total_games']} games")
print(f"  30-day: {metrics['rolling_30d']['accuracy']:.1%} accuracy | {metrics['rolling_30d']['ev_realized']:+.1%} realized EV | {metrics['rolling_30d']['total_games']} games")
cw = ", ".join(f"{c['id']}={c['weight']}" for c in challengers)
print(f"  Challengers: {cw}")
gcount = len(assumptions.get("graveyard", []))
print(f"  Graveyard: {gcount} retired variants")

print(f"\n  NOTE: This analysis is for entertainment purposes only.")
print(f"  Past performance does not guarantee future results.")
