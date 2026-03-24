#!/usr/bin/env python3
"""
Edge-Finder Monte Carlo Simulation Engine

Runs N simulations of a game given team ratings and assumption parameters.
Outputs JSON with win probabilities, expected margin, EV calculations, and
confidence intervals.

Usage:
    python sim.py --game '{"home": {...}, "away": {...}, "odds": {...}, "params": {...}}'
    python sim.py --batch games.json

The sim models each game as:
    home_score ~ N(home_rating * pace_factor + home_adv, stddev)
    away_score ~ N(away_rating * pace_factor, stddev)

Where ratings, pace, home_adv, and stddev are derived from team stats
and adjusted by the assumption parameters.
"""

import argparse
import json
import math
import sys
from dataclasses import dataclass, asdict
from typing import Optional

import random

# ── Sport-specific constants ──────────────────────────────────────────────

SPORT_DEFAULTS = {
    "basketball_nba": {
        "avg_score": 112.0,
        "stddev": 12.5,
        "home_advantage": 3.0,
        "avg_pace": 100.0,  # possessions per game
    },
    "baseball_mlb": {
        "avg_score": 4.5,
        "stddev": 2.8,
        "home_advantage": 0.3,
        "avg_pace": 1.0,  # not really applicable, placeholder
    },
    "icehockey_nhl": {
        "avg_score": 3.1,
        "stddev": 1.6,
        "home_advantage": 0.25,
        "avg_pace": 1.0,
    },
    "americanfootball_nfl": {
        "avg_score": 23.0,
        "stddev": 10.0,
        "home_advantage": 2.5,
        "avg_pace": 1.0,
    },
}


@dataclass
class TeamStats:
    name: str
    season_ppg: float           # points per game (season)
    season_opp_ppg: float       # opponent points per game (season)
    last10_ppg: float           # last 10 games ppg
    last10_opp_ppg: float       # last 10 games opponent ppg
    season_pace: float          # possessions/game or equivalent
    home_record_pct: float      # win% at home (0-1)
    away_record_pct: float      # win% on road (0-1)
    is_back_to_back: bool       # playing 2nd night of B2B
    key_injuries: int           # count of significant absences (0-5 scale)


@dataclass
class OddsData:
    spread_home: float          # e.g., -3.5 means home favored by 3.5
    ml_home: int                # moneyline for home (e.g., -150)
    ml_away: int                # moneyline for away (e.g., +130)
    total: float                # over/under total
    book: str                   # which sportsbook


@dataclass
class SimParams:
    recency_weight: float       # 1.0 = season only, 2.0 = last10 weighted 2x
    injury_discount: float      # 0.0 = ignore, 1.0 = full impact
    home_advantage_adjustment: float  # added to baseline home advantage
    regression_to_mean: float   # 0.0 = none, 0.2 = regress 20% to league avg
    pace_adjustment: str        # "season_average" or "opponent_adjusted"


@dataclass
class SimResult:
    home_team: str
    away_team: str
    home_win_prob: float
    away_win_prob: float
    expected_margin: float      # positive = home favored
    margin_stddev: float
    spread_ev_home: float       # EV of betting home spread
    spread_ev_away: float
    ml_ev_home: float           # EV of betting home ML
    ml_ev_away: float
    ev_ci_lower: float          # 95% CI lower bound on best EV
    ev_ci_upper: float          # 95% CI upper bound on best EV
    n_sims: int
    model_id: str


def ml_to_implied_prob(ml: int) -> float:
    """Convert American moneyline to implied probability."""
    if ml > 0:
        return 100.0 / (ml + 100.0)
    else:
        return abs(ml) / (abs(ml) + 100.0)


def compute_team_rating(stats: TeamStats, params: SimParams, league_avg: float) -> float:
    """
    Compute an adjusted scoring rating for a team.
    Blends season and recent stats based on recency_weight.
    Applies regression to mean if specified.
    """
    # Blend season and recent offensive rating
    total_weight = 1.0 + params.recency_weight
    off_rating = (stats.season_ppg + params.recency_weight * stats.last10_ppg) / total_weight

    # Regression to mean
    if params.regression_to_mean > 0:
        off_rating = off_rating * (1 - params.regression_to_mean) + league_avg * params.regression_to_mean

    return off_rating


def compute_def_rating(stats: TeamStats, params: SimParams, league_avg: float) -> float:
    """
    Compute adjusted defensive rating (opponent PPG — lower is better defense).
    """
    total_weight = 1.0 + params.recency_weight
    def_rating = (stats.season_opp_ppg + params.recency_weight * stats.last10_opp_ppg) / total_weight

    if params.regression_to_mean > 0:
        def_rating = def_rating * (1 - params.regression_to_mean) + league_avg * params.regression_to_mean

    return def_rating


def simulate_game(
    home: TeamStats,
    away: TeamStats,
    odds: OddsData,
    params: SimParams,
    sport: str,
    model_id: str,
    n_sims: int = 50000,
) -> SimResult:
    """
    Run Monte Carlo simulation of a single game.

    Model:
        home_expected = (home_off * away_def / league_avg) + home_adv - injury_penalty
        away_expected = (away_off * home_def / league_avg) - injury_penalty
        Each game: scores drawn from normal distribution around expected values.
    """
    defaults = SPORT_DEFAULTS.get(sport, SPORT_DEFAULTS["basketball_nba"])
    league_avg = defaults["avg_score"]
    base_stddev = defaults["stddev"]
    base_home_adv = defaults["home_advantage"]

    # Compute adjusted ratings
    home_off = compute_team_rating(home, params, league_avg)
    home_def = compute_def_rating(home, params, league_avg)
    away_off = compute_team_rating(away, params, league_avg)
    away_def = compute_def_rating(away, params, league_avg)

    # Expected scores using the "four factors" style:
    # home_expected = home_offense * away_defense / league_avg
    # This means a great offense vs bad defense = high score
    home_expected = (home_off * away_def) / league_avg if league_avg > 0 else home_off
    away_expected = (away_off * home_def) / league_avg if league_avg > 0 else away_off

    # Home advantage
    home_adv = base_home_adv + params.home_advantage_adjustment

    # Injury discount: each key injury costs ~2-4% of scoring for NBA,
    # proportionally less for lower-scoring sports
    injury_cost_per = base_stddev * 0.15  # ~1.9 pts in NBA
    if params.injury_discount > 0:
        home_expected -= home.key_injuries * injury_cost_per * params.injury_discount
        away_expected -= away.key_injuries * injury_cost_per * params.injury_discount

    # Back-to-back penalty
    if params.injury_discount > 0:
        b2b_penalty = base_stddev * 0.2  # ~2.5 pts in NBA
        if home.is_back_to_back:
            home_expected -= b2b_penalty * params.injury_discount
        if away.is_back_to_back:
            away_expected -= b2b_penalty * params.injury_discount

    # Pace adjustment (only meaningful for NBA currently)
    if params.pace_adjustment == "opponent_adjusted" and sport == "basketball_nba":
        # Adjust expected scores by the matchup's pace relative to league average
        matchup_pace = (home.season_pace + away.season_pace) / 2
        pace_factor = matchup_pace / defaults["avg_pace"] if defaults["avg_pace"] > 0 else 1.0
        home_expected *= pace_factor
        away_expected *= pace_factor

    # Apply home advantage
    home_expected += home_adv

    # Run simulations
    home_wins = 0
    margins = []

    for _ in range(n_sims):
        h_score = random.gauss(home_expected, base_stddev)
        a_score = random.gauss(away_expected, base_stddev)

        # Floor scores at 0
        h_score = max(0, h_score)
        a_score = max(0, a_score)

        margin = h_score - a_score
        margins.append(margin)

        if margin > 0:
            home_wins += 1
        elif margin == 0:
            # Tie goes to coin flip (rare with continuous distribution)
            if random.random() < 0.5:
                home_wins += 1

    home_win_prob = home_wins / n_sims
    away_win_prob = 1.0 - home_win_prob
    expected_margin = sum(margins) / n_sims
    margin_stddev = (sum((m - expected_margin) ** 2 for m in margins) / n_sims) ** 0.5

    # EV calculations
    implied_home = ml_to_implied_prob(odds.ml_home)
    implied_away = ml_to_implied_prob(odds.ml_away)

    # ML EV: (model_prob * payout) - (1 - model_prob) * stake
    # For American odds: if +130, you win $130 on $100 bet
    # if -150, you win $100 on $150 bet (i.e., $66.67 on $100)
    def ml_payout(ml: int) -> float:
        """Return profit on a $1 bet if you win."""
        if ml > 0:
            return ml / 100.0
        else:
            return 100.0 / abs(ml)

    ml_ev_home = home_win_prob * ml_payout(odds.ml_home) - (1 - home_win_prob)
    ml_ev_away = away_win_prob * ml_payout(odds.ml_away) - (1 - away_win_prob)

    # Spread EV: probability of covering the spread
    spread = odds.spread_home  # negative means home favored
    covers_home = sum(1 for m in margins if m + spread > 0) / n_sims  # home covers
    covers_away = 1.0 - covers_home
    # Standard -110 spread bet pays ~0.909 on $1
    spread_payout = 0.909
    spread_ev_home = covers_home * spread_payout - (1 - covers_home)
    spread_ev_away = covers_away * spread_payout - (1 - covers_away)

    # 95% CI on the best EV (using normal approximation)
    best_ev = max(ml_ev_home, ml_ev_away, spread_ev_home, spread_ev_away)
    # Standard error of EV estimate ≈ stddev / sqrt(n)
    se = margin_stddev / math.sqrt(n_sims) / league_avg if league_avg > 0 else 0.01
    ev_ci_lower = best_ev - 1.96 * se
    ev_ci_upper = best_ev + 1.96 * se

    return SimResult(
        home_team=home.name,
        away_team=away.name,
        home_win_prob=round(home_win_prob, 4),
        away_win_prob=round(away_win_prob, 4),
        expected_margin=round(expected_margin, 2),
        margin_stddev=round(margin_stddev, 2),
        spread_ev_home=round(spread_ev_home, 4),
        spread_ev_away=round(spread_ev_away, 4),
        ml_ev_home=round(ml_ev_home, 4),
        ml_ev_away=round(ml_ev_away, 4),
        ev_ci_lower=round(ev_ci_lower, 4),
        ev_ci_upper=round(ev_ci_upper, 4),
        n_sims=n_sims,
        model_id=model_id,
    )


def run_single_game(game_data: dict) -> dict:
    """
    Run simulation for a single game from JSON input.

    Expected game_data format:
    {
        "sport": "basketball_nba",
        "model_id": "recency-v1",
        "home": { TeamStats fields },
        "away": { TeamStats fields },
        "odds": { OddsData fields },
        "params": { SimParams fields },
        "n_sims": 50000
    }
    """
    home = TeamStats(**game_data["home"])
    away = TeamStats(**game_data["away"])
    odds = OddsData(**game_data["odds"])
    params = SimParams(**game_data["params"])
    sport = game_data.get("sport", "basketball_nba")
    model_id = game_data.get("model_id", "unknown")
    n_sims = game_data.get("n_sims", 50000)

    result = simulate_game(home, away, odds, params, sport, model_id, n_sims)
    return asdict(result)


def run_batch(games: list[dict]) -> list[dict]:
    """Run simulations for multiple games."""
    return [run_single_game(g) for g in games]


def main():
    parser = argparse.ArgumentParser(description="Edge-Finder Monte Carlo Sim")
    parser.add_argument("--game", type=str, help="Single game JSON string")
    parser.add_argument("--batch", type=str, help="Path to batch games JSON file")
    args = parser.parse_args()

    if args.game:
        game_data = json.loads(args.game)
        result = run_single_game(game_data)
        print(json.dumps(result, indent=2))
    elif args.batch:
        with open(args.batch) as f:
            games = json.load(f)
        results = run_batch(games)
        print(json.dumps(results, indent=2))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
