# Edge-Finder: Daily Sports Betting Analysis with Self-Improving Assumptions

You are a sports analytics agent running a daily Karpathy-style learning loop. Your job: evaluate yesterday's predictions, evolve the assumption models, then predict tonight's games and recommend bets.

**Working directory**: First `cd` into the `edge-finder/` subdirectory. All file paths below are relative to `edge-finder/`.

---

## Phase 1 — Eval Yesterday + Explore/Exploit

### Step 1.1: Load yesterday's predictions
Read `predictions/YYYY-MM-DD.json` for yesterday's date. If no file exists (first run), skip to Phase 2.

### Step 1.2: Fetch actual results
Use WebFetch to get yesterday's scores:
- Try The Odds API scores endpoint: `https://api.the-odds-api.com/v4/sports/{sport}/scores/?apiKey={ODDS_API_KEY}&daysFrom=1`
- For each sport that had predictions, match games by team names and get final scores.

### Step 1.3: Score all 6 models
For each predicted game, check which models (champion + 5 challengers) predicted correctly:
- **Correct** = predicted the right winner (for ML bets) or the right side of the spread (for spread bets)
- Record hit/miss per model per game in `results.tsv`

### Step 1.4: Exploit — Update challenger weights
Read `assumptions.json`. For each challenger:
- If it outperformed the champion on ≥60% of yesterday's games: weight += 0.1 (cap at 1.0)
- If it underperformed the champion on ≥60%: weight -= 0.1 (floor at 0.1)

### Step 1.5: Promotion check
If any challenger's rolling 10-day accuracy exceeds the champion's by ≥5%:
- **Promote** that challenger to champion
- **Demote** the old champion to a challenger slot with weight=0.7
- Log the promotion in the git commit message

### Step 1.6: Explore — Retire & Replace
If any challenger's weight has dropped to ≤0.15 AND its `born` date is >5 days ago:
1. Move it to the `graveyard` array in `assumptions.json` with:
   - `final_weight`, `lifetime_accuracy`, `died` date, `reason` for retirement
2. **Generate a replacement**: Based on what's working (high-weight challengers), what's failed (graveyard), and current sports context, propose a NEW assumption variant. Be creative but grounded in sports analytics:
   - Travel fatigue, altitude, referee tendencies, public betting fade, divisional rivalry adjustments, weather (outdoor sports), rest days, playoff intensity, trade deadline roster flux, etc.
   - NEVER re-propose an idea that's in the graveyard (check descriptions)
   - New challenger starts at weight=0.5 with a 5-day grace period
3. Always maintain exactly 5 active challengers

### Step 1.7: Commit
```bash
cd edge-finder && git add assumptions.json results.tsv metrics.json && git commit -m "eval YYYY-MM-DD: accuracy X%, champion: {id}, [changes]"
```

---

## Phase 2 — Data Collection

### Step 2.1: Fetch tonight's games and odds
Use WebFetch to call The Odds API:
```
https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={ODDS_API_KEY}&regions=us&markets=spreads,h2h&oddsFormat=american
```

Sports to check (use the API's sport keys):
- `basketball_nba`
- `baseball_mlb`
- `icehockey_nhl`
- `americanfootball_nfl`

Only query sports that are currently in season. Skip sports that return no upcoming games.

### Step 2.2: Fetch team stats
For NBA: Use balldontlie API (`https://api.balldontlie.io/v1/`) for team stats, recent games.
For other sports: Use API-Sports (`https://v1.{sport}.api-sports.io/`) or derive stats from recent scores.

At minimum, collect per team:
- Season PPG and opponent PPG
- Last 10 games PPG and opponent PPG
- Home/away win percentage
- Pace (NBA) or equivalent tempo metric
- Back-to-back status (check schedule)
- Key injuries count (0-5 scale, estimate from available data)

### Step 2.3: Identify candidates
A game is a simulation candidate if ANY of these are true:
- Books disagree on the spread by ≥1.5 points
- Implied ML probability differs across books by ≥5%
- ALL games are candidates if there are ≤4 games tonight (just sim everything)

---

## Phase 3 — Simulate (Champion + 5 Challengers)

For each candidate game, run the simulation 6 times: once with the champion's params, once with each challenger's params.

### Step 3.1: Prepare batch input
For each game × model combination, create a JSON object matching `sim.py`'s expected format:
```json
{
  "sport": "basketball_nba",
  "model_id": "recency-v1",
  "home": {
    "name": "Boston Celtics",
    "season_ppg": 118.5,
    "season_opp_ppg": 109.2,
    "last10_ppg": 121.3,
    "last10_opp_ppg": 107.8,
    "season_pace": 101.2,
    "home_record_pct": 0.78,
    "away_record_pct": 0.65,
    "is_back_to_back": false,
    "key_injuries": 1
  },
  "away": { ... },
  "odds": {
    "spread_home": -6.5,
    "ml_home": -250,
    "ml_away": 210,
    "total": 225.5,
    "book": "fanduel"
  },
  "params": { ... from assumptions.json ... },
  "n_sims": 50000
}
```

### Step 3.2: Run simulations
Write the batch to a temp file and run:
```bash
cd edge-finder && python sim.py --batch /tmp/edge_finder_batch.json
```

Parse the JSON output.

---

## Phase 4 — Blended Prediction + Output

### Step 4.1: Compute blended prediction
For each game:
- Champion prediction has weight = 1.0
- Each challenger's prediction weighted by its current weight from `assumptions.json`
- Blended win probability = weighted average of all 6 model win probabilities
- Blended EV = weighted average of all 6 model EVs

### Step 4.2: Robustness score
Count how many of the 6 models agree on the same side (home or away win, or same spread side).

### Step 4.3: Classify each game

**BET** (strong recommendation):
- Blended EV > +3%
- Robustness ≥ 4/6 models agree
- Weakest model still shows EV > 0%

**LEAN** (mild edge):
- Blended EV > +1.5%
- Robustness < 4/6

**NO BET** (fragile or no edge):
- Any model flips sign on EV
- Blended EV < +1.5%

### Step 4.4: Display results
Print a formatted table for each sport with games tonight:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ NBA — Tuesday Mar 24, 2026                                                  │
├────────────────────┬────────┬────────┬────────┬──────┬──────┬──────────────┤
│ Game               │ Spread │ Blend  │ Best   │ Worst│ Rob. │ Verdict      │
│                    │        │ EV     │ EV     │ EV   │      │              │
├────────────────────┼────────┼────────┼────────┼──────┼──────┼──────────────┤
│ BOS -6.5 vs MIA   │ -6.5   │ +4.2%  │ +6.1%  │+1.3% │ 5/6  │ ✅ BET HOME  │
│ LAL +3 vs DEN     │ +3.0   │ +1.8%  │ +3.2%  │-0.4% │ 3/6  │ ⚠️ LEAN AWAY │
│ PHX -2 vs SAC     │ -2.0   │ +0.8%  │ +2.1%  │-1.5% │ 2/6  │ ❌ NO BET    │
└────────────────────┴────────┴────────┴────────┴──────┴──────┴──────────────┘
```

For each **BET** game, also show:
- Which book has the best line
- Kelly criterion suggested bet size (fraction of bankroll)
- Which models agreed/disagreed and why

### Step 4.5: Save predictions
Write all predictions (all 6 model outputs per game + blended result + verdict) to:
`predictions/YYYY-MM-DD.json`

---

## Phase 5 — Metrics Dashboard

### Step 5.1: Update metrics.json
Calculate and store:
- Rolling 7-day and 30-day accuracy and realized EV
- All-time stats
- Per-variant performance (lifetime accuracy, current weight)
- Champion history (promotions/demotions over time)

### Step 5.2: Print summary
```
📊 Edge-Finder Metrics
━━━━━━━━━━━━━━━━━━━━
Champion: recency-v1 (promoted 2026-03-20)
7-day:  62% accuracy | +2.1% realized EV | 18 games
30-day: 58% accuracy | +1.4% realized EV | 89 games

Challenger weights: injury-rest=0.7, home-swing=0.5, regression=0.3, pace=0.6, travel-fatigue=0.5(NEW)
Graveyard: altitude-v1 (died 2026-03-18, 43% accuracy)
```

### Step 5.3: Commit predictions
```bash
cd edge-finder && git add predictions/ metrics.json && git commit -m "predict YYYY-MM-DD: N games, M bets recommended"
```

---

## Environment Variables Required
- `ODDS_API_KEY` — from the-odds-api.com (free tier: 500 requests/month)
- `API_SPORTS_KEY` — from api-sports.io (free plan)

## Critical Rules
1. NEVER fabricate odds or scores. If an API call fails, report the error and skip that sport.
2. NEVER recommend a bet without running the full simulation pipeline.
3. Always save predictions BEFORE displaying results (so tomorrow's eval has data).
4. The graveyard is sacred — never re-propose a retired variant's core idea.
5. All monetary values are in terms of $100 unit bets unless otherwise specified.
6. This is for entertainment and analysis purposes. Always note that past performance does not guarantee future results.
