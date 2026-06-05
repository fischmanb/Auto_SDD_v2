#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-06-05.
Phase 1: SKIPPED — no predictions for yesterday (2026-06-04).
Phase 2-5: Simulate tonight's games, produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(os.path.abspath(__file__))
TODAY = "2026-06-05"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — SKIPPED (no predictions for 2026-06-04)
# ════════════════════════════════════════════════════════════════════════

print("=" * 90)
print(" PHASE 1 — No predictions found for 2026-06-04, skipping evaluation")
print("=" * 90)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

# ════════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (June 5, 2026)
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 90}")
print(f" PHASE 2-5 — Predicting games for {TODAY}")
print(f"{'=' * 90}")

# ── Tonight's games with live odds from web searches ─────────────────
# Sources: FanDuel, CBS Sports, NBC Sports, BetMGM, OddsShark, Covers
#
# Sports in season: NBA (Finals), MLB (regular season)
# NHL: off tonight (Stanley Cup Finals Game 3 is June 6)
# NFL: offseason

games_raw = [
    # === NBA Finals Game 2: Knicks @ Spurs ===
    # Series: NYK leads 1-0 (won Game 1 105-95 in San Antonio)
    # SAS home. Spread: SAS -6.0, ML: NYK +190 / SAS -225, O/U 216
    # NYK: 123.3 OffRtg (playoffs #1), 103.5 DefRtg (playoffs #1)
    #   outscoring opponents by 19.4 ppg (playoff history best)
    #   11-game win streak entering Finals, won G1 on road
    #   Brunson: 26.9 PPG playoffs, healthy. KAT: healthy, double-double G1
    #   Robinson: fractured pinkie (playing with brace)
    # SAS: 115.4 OffRtg, 104.4 DefRtg. Wemby 23.2 PPG playoffs
    #   Wemby: 6-21 FG in Game 1, struggled. No injuries listed.
    #   Home team, looking to even series.
    {
        "sport": "basketball_nba",
        "home": {
            "name": "San Antonio Spurs",
            "season_ppg": 113.5,
            "season_opp_ppg": 110.0,
            "last10_ppg": 112.0,
            "last10_opp_ppg": 105.0,
            "season_pace": 100.5,
            "home_record_pct": 0.700,
            "away_record_pct": 0.540,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "New York Knicks",
            "season_ppg": 114.5,
            "season_opp_ppg": 108.0,
            "last10_ppg": 118.0,
            "last10_opp_ppg": 98.5,
            "season_pace": 99.5,
            "home_record_pct": 0.750,
            "away_record_pct": 0.650,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -6.0,
            "ml_home": -225,
            "ml_away": 190,
            "total": 216.0,
            "book": "fanduel"
        }
    },

    # === MLB Games (15 games) ===
    # Team stats estimated from current records (as of June 4-5, 2026)
    # RPG formula: 4.5 + (win_pct - 0.5) * 3.0

    # 1. SF Giants (25-38) @ CHC Cubs (33-30)
    # CHC -162, SF +135. Cabrera vs Robbie Ray.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago Cubs",
            "season_ppg": 4.57,
            "season_opp_ppg": 4.43,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "San Francisco Giants",
            "season_ppg": 4.19,
            "season_opp_ppg": 4.81,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.450,
            "away_record_pct": 0.350,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -162,
            "ml_away": 135,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 2. SEA Mariners (33-29) @ DET Tigers (25-38)
    # SEA -130, DET +110. SEA on 7-game win streak.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Detroit Tigers",
            "season_ppg": 4.19,
            "season_opp_ppg": 4.81,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 5.1,
            "season_pace": 1.0,
            "home_record_pct": 0.450,
            "away_record_pct": 0.350,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Seattle Mariners",
            "season_ppg": 4.60,
            "season_opp_ppg": 4.40,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 110,
            "ml_away": -130,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 3. CWS White Sox (33-29) @ PHI Phillies (32-29)
    # PHI -188, CWS +158. PHI -1.5 (+108). O/U 8.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.58,
            "season_opp_ppg": 4.42,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Chicago White Sox",
            "season_ppg": 4.60,
            "season_opp_ppg": 4.40,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -188,
            "ml_away": 158,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 4. BOS Red Sox (26-34) @ NYY Yankees (36-25)
    # NYY -144, BOS +122. CRITICAL: Aaron Judge OUT (stress fracture, 4-6 wks)
    # NYY relying on Ben Rice (.300/.393/.638, 17 HR). Judge absence = injuries 5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Yankees",
            "season_ppg": 4.77,
            "season_opp_ppg": 4.23,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.640,
            "away_record_pct": 0.540,
            "is_back_to_back": False,
            "key_injuries": 5
        },
        "away": {
            "name": "Boston Red Sox",
            "season_ppg": 4.30,
            "season_opp_ppg": 4.70,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -144,
            "ml_away": 122,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 5. BAL Orioles (29-33) @ TOR Blue Jays (29-33)
    # TOR -149, BAL +124. TOR -1.5 (+135). O/U 8.0.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.40,
            "season_opp_ppg": 4.60,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.420,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.40,
            "season_opp_ppg": 4.60,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.7,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.420,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -149,
            "ml_away": 124,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 6. TB Rays (36-22) @ MIA Marlins (29-34)
    # TB -138, MIA +118. Rasmussen 3-0 career vs MIA.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Miami Marlins",
            "season_ppg": 4.38,
            "season_opp_ppg": 4.62,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.410,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.86,
            "season_opp_ppg": 4.14,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.670,
            "away_record_pct": 0.570,
            "is_back_to_back": False,
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

    # 7. PIT Pirates (33-29) @ ATL Braves (42-20)
    # ATL -140, PIT +120. ATL best record in MLB.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Atlanta Braves",
            "season_ppg": 5.03,
            "season_opp_ppg": 3.97,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.730,
            "away_record_pct": 0.620,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.60,
            "season_opp_ppg": 4.40,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -140,
            "ml_away": 120,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 8. ATH Athletics (30-31) @ HOU Astros (28-35)
    # Pick'em: HOU -108, ATH -108. Lambert vs Perkins.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Houston Astros",
            "season_ppg": 4.33,
            "season_opp_ppg": 4.67,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 4.9,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Athletics",
            "season_ppg": 4.48,
            "season_opp_ppg": 4.52,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -108,
            "ml_away": -108,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 9. CIN Reds (31-30) @ STL Cardinals (32-28)
    # STL -142, CIN +120. STL home at Busch Stadium.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.60,
            "season_opp_ppg": 4.40,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.52,
            "season_opp_ppg": 4.48,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -142,
            "ml_away": 120,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 10. CLE Guardians (36-28) @ TEX Rangers (30-32)
    # Near pick'em. CLE -110, TEX -110 (estimated).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Texas Rangers",
            "season_ppg": 4.45,
            "season_opp_ppg": 4.55,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.69,
            "season_opp_ppg": 4.31,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.610,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -110,
            "ml_away": -110,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 11. KC Royals (24-38) @ MIN Twins (29-34)
    # MIN -118, KC +100. Both struggling teams.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Minnesota Twins",
            "season_ppg": 4.38,
            "season_opp_ppg": 4.62,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.410,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Kansas City Royals",
            "season_ppg": 4.16,
            "season_opp_ppg": 4.84,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 5.2,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.340,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -118,
            "ml_away": 100,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 12. MIL Brewers (37-22) @ COL Rockies (24-39)
    # MIL -144, COL +122. Coors Field (altitude).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Colorado Rockies",
            "season_ppg": 4.14,
            "season_opp_ppg": 4.86,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 5.5,
            "season_pace": 1.0,
            "home_record_pct": 0.430,
            "away_record_pct": 0.330,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.88,
            "season_opp_ppg": 4.12,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.680,
            "away_record_pct": 0.570,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 122,
            "ml_away": -144,
            "total": 10.0,
            "book": "fanduel"
        }
    },

    # 13. WSH Nationals (31-32) @ AZ Diamondbacks (32-29)
    # AZ -140, WSH +120. AZ -1.5 (+167).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.58,
            "season_opp_ppg": 4.42,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Washington Nationals",
            "season_ppg": 4.48,
            "season_opp_ppg": 4.52,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -140,
            "ml_away": 120,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 14. NYM Mets (27-35) @ SD Padres (32-28)
    # SD -124, NYM +106. At Petco Park.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Diego Padres",
            "season_ppg": 4.60,
            "season_opp_ppg": 4.40,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "New York Mets",
            "season_ppg": 4.31,
            "season_opp_ppg": 4.69,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 4.9,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -124,
            "ml_away": 106,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 15. LAD Dodgers (40-22) @ LAA Angels (24-39)
    # LAD -188, LAA +158. LAD -1.5 (+116). O/U 8.5.
    # Freeway Series. Ohtani faces former team.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Angels",
            "season_ppg": 4.14,
            "season_opp_ppg": 4.86,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 5.1,
            "season_pace": 1.0,
            "home_record_pct": 0.430,
            "away_record_pct": 0.330,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 4.94,
            "season_opp_ppg": 4.06,
            "last10_ppg": 5.1,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.700,
            "away_record_pct": 0.590,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 158,
            "ml_away": -188,
            "total": 8.5,
            "book": "fanduel"
        }
    },
]

# ── Build batch ─────────────────────────────────────────────────────
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

# ── Organize results by game ────────────────────────────────────────
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

# ── Compute blended predictions ─────────────────────────────────────
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
        w = 1.0 if mid == champion["id"] else next(c["weight"] for c in challengers if c["id"] == mid)
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

# ── Save predictions BEFORE displaying ──────────────────────────────
pred_file = os.path.join(BASE, "predictions", f"{TODAY}.json")
pred_data = {"date": TODAY, "predictions": predictions}
with open(pred_file, "w") as f:
    json.dump(pred_data, f, indent=2)
print(f"\nPredictions saved to predictions/{TODAY}.json")

# ── Display results ─────────────────────────────────────────────────
sports_order = ["basketball_nba", "baseball_mlb"]
sport_names = {"basketball_nba": "NBA", "baseball_mlb": "MLB"}
sport_dates = {"basketball_nba": "Friday June 5, 2026", "baseball_mlb": "Friday June 5, 2026"}

for sport in sports_order:
    sport_preds = [p for p in predictions if p["sport"] == sport]
    if not sport_preds:
        continue

    name = sport_names[sport]
    print(f"\n{'=' * 90}")
    print(f" {name} — {sport_dates[sport]}")
    print(f"{'=' * 90}")
    print(f" {'Game':<32} {'Spread':>7} {'Blend EV':>9} {'Best EV':>8} {'Worst':>7} {'Rob.':>5}  {'Verdict':<16}")
    print(f" {'-'*32} {'-'*7} {'-'*9} {'-'*8} {'-'*7} {'-'*5}  {'-'*16}")

    bets = []
    for p in sport_preds:
        spread = p["odds"]["spread_home"]
        home_short = p["home_team"].split()[-1][:6]
        away_short = p["away_team"].split()[-1][:6]

        if spread < 0:
            game_str = f"{home_short} {spread:+.1f} vs {away_short}"
        elif spread > 0:
            game_str = f"{away_short} @ {home_short} (+{spread:.1f})"
        else:
            game_str = f"{away_short} @ {home_short}"

        if p["verdict"] == "BET":
            icon = " >>>"
        elif p["verdict"] == "LEAN":
            icon = "  > "
        else:
            icon = "  - "

        verdict_str = f"{icon} {p['verdict']} {p['side']}"

        print(f" {game_str:<32} {spread:>+7.1f} {p['best_blend_ev']:>+8.1%} {p['best_model_ev']:>+7.1%} {p['worst_model_ev']:>+6.1%} {p['robustness']:>5} {verdict_str:<16}")

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
                print(f"    {mid:<20} WP={mr['home_win_prob']:.1%} Mrgn={mr['expected_margin']:+.1f} BestEV={best:+.1%} Agree={agree}")

# ── Update metrics.json ─────────────────────────────────────────────
metrics_file = os.path.join(BASE, "metrics.json")
with open(metrics_file) as f:
    metrics = json.load(f)

total_bets_today = sum(1 for p in predictions if p["verdict"] == "BET")
total_leans_today = sum(1 for p in predictions if p["verdict"] == "LEAN")
total_no_today = sum(1 for p in predictions if p["verdict"] == "NO BET")

metrics["last_updated"] = TODAY
metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": total_bets_today,
    "leans": total_leans_today,
    "sports": list(set(p["sport"] for p in predictions)),
    "notes": f"NBA Finals G2 (NYK@SAS) + {sum(1 for p in predictions if p['sport']=='baseball_mlb')} MLB games. {total_bets_today} BETs, {total_leans_today} LEANs, {total_no_today} NO BETs."
}

with open(metrics_file, "w") as f:
    json.dump(metrics, f, indent=2)

# ── Summary stats ───────────────────────────────────────────────────
print(f"\n{'=' * 90}")
print(f" SUMMARY: {len(predictions)} games analyzed | {total_bets_today} BETs | {total_leans_today} LEANs | {total_no_today} NO BETs")
print(f"{'=' * 90}")

print(f"\n  Edge-Finder Metrics")
print(f"  {'=' * 50}")
print(f"  Champion: {champion['id']} (promoted {champion['promoted_on']})")
print(f"  All-time: {metrics['all_time']['total_correct']}/{metrics['all_time']['total_games']} = {metrics['all_time']['accuracy']:.1%} accuracy")
print(f"  All-time bets: {metrics['all_time']['total_bets_won']}/{metrics['all_time']['total_bets_recommended']} won")
cw = ", ".join(f"{c['id'].replace('-v1','')}={c['weight']}" for c in challengers)
print(f"  Challengers: {cw}")
gcount = len(assumptions.get("graveyard", []))
print(f"  Graveyard: {gcount} retired variants")

print(f"\n  NOTE: This analysis is for entertainment purposes only.")
print(f"  Past performance does not guarantee future results.")
