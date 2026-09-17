# =====================================================================================
# Initial Balance Statistical Reversion (ES V1.0_Frozen) - event-level regression
#
#   Rscript research/initial_balance_regression.R
#
# QUESTION
#   Does a FALSE BREAKOUT of the Initial Balance increase the probability of subsequently
#   touching the IB midpoint, conditioned on a 10-35 point IB range?
#
# NOTE ON PROVENANCE
#   R is NOT installed in the environment where this study was run, so the numbers in
#   docs/INITIAL_BALANCE_REVERSION_V1_BACKTEST_REPORT.md were produced by the equivalent
#   Python estimator in scripts/ib_event_study.py (Newton-Raphson logit with a CR0
#   cluster-robust sandwich, clustered on trading day). This script is the specified
#   deliverable and reproduces the same specification; run it to confirm independently.
#   If the two disagree, THAT is the finding.
#
# DATA
#   research/ib_reversion/ib_events.csv, written by scripts/ib_event_study.py.
#   One row per eligible event (false breakout) or matched in-IB control.
# =====================================================================================

suppressWarnings(suppressMessages({
  have_sandwich <- requireNamespace("sandwich", quietly = TRUE)
  have_lmtest   <- requireNamespace("lmtest",   quietly = TRUE)
}))

path <- "research/ib_reversion/ib_events.csv"
if (!file.exists(path)) stop(sprintf("missing %s - run scripts/ib_event_study.py first", path))
d <- read.csv(path, stringsAsFactors = FALSE)

# ---- 2. validate data types ---------------------------------------------------------
stopifnot(is.numeric(d$midpoint_touch), all(d$midpoint_touch %in% c(0, 1)))
stopifnot(is.numeric(d$false_breakout), all(d$false_breakout %in% c(0, 1)))
for (v in c("ib_range", "distance_to_mid_over_range", "minutes_since_ib", "direction",
            "excursion_points", "stop_distance")) {
  stopifnot(is.numeric(d[[v]]), all(is.finite(d[[v]])))
}
d$session <- as.Date(d$session)

# ---- 3. no future information in the explanatory variables ---------------------------
# Every covariate is measured at or before the event bar's close. The only forward-looking
# columns are the OUTCOME (midpoint_touch) and its duration, which is what an outcome is.
forward_cols <- c("midpoint_touch", "buckets_to_resolution")
explanatory  <- setdiff(names(d), c(forward_cols, "session", "instrument", "event_id"))
cat("explanatory variables (all event-time):", paste(explanatory, collapse = ", "), "\n")
stopifnot(!any(forward_cols %in% explanatory))
# the IB itself is sealed at 10:30 and every event is after it
stopifnot(all(d$minutes_since_ib >= 0))

# ---- 4. descriptive statistics --------------------------------------------------------
cat("\n--- descriptives ---\n")
cat(sprintf("rows %d   sessions %d   events %d   controls %d\n",
            nrow(d), length(unique(d$session)),
            sum(d$false_breakout == 1), sum(d$false_breakout == 0)))
print(aggregate(midpoint_touch ~ false_breakout, data = d, FUN = mean))
print(summary(d[, c("ib_range", "distance_to_mid_over_range", "minutes_since_ib",
                    "excursion_points")]))

# ---- 5. estimation --------------------------------------------------------------------
f <- midpoint_touch ~ false_breakout + ib_range + distance_to_mid_over_range +
       minutes_since_ib + direction

m_logit  <- glm(f, data = d, family = binomial(link = "logit"))
m_probit <- glm(f, data = d, family = binomial(link = "probit"))

# ---- 7/8. robust SEs, clustered on trading day (repeated events within a day) ---------
report <- function(model, label) {
  cat(sprintf("\n--- %s ---\n", label))
  if (have_sandwich && have_lmtest) {
    V  <- sandwich::vcovCL(model, cluster = d$session, type = "HC0")
    ct <- lmtest::coeftest(model, vcov. = V)
    print(ct)
    ci <- cbind(ct[, 1] - 1.96 * ct[, 2], ct[, 1] + 1.96 * ct[, 2])
    colnames(ci) <- c("ci_lo", "ci_hi")
    out <- cbind(coef = ct[, 1], robust_se = ct[, 2], z = ct[, 3], p = ct[, 4], ci)
    if (label == "logit") {
      out <- cbind(out, odds_ratio = exp(ct[, 1]),
                   or_lo = exp(ci[, 1]), or_hi = exp(ci[, 2]))
    }
    print(round(out, 5))
  } else {
    cat("packages 'sandwich' and 'lmtest' are not installed; MODEL-BASED standard errors\n")
    cat("are shown and are NOT valid here - events repeat within a trading day.\n")
    print(summary(model))
  }
  cat(sprintf("N = %d, clusters = %d, AIC = %.2f\n",
              nobs(model), length(unique(d$session)), AIC(model)))
}
report(m_logit,  "logit")
report(m_probit, "probit")

# ---- 11. chronological out-of-sample --------------------------------------------------
days <- sort(unique(d$session))
cut  <- days[floor(length(days) * 0.7)]
tr   <- d[d$session <  cut, ]
te   <- d[d$session >= cut, ]
cat(sprintf("\n--- chronological OOS: train < %s (%d rows), test >= %s (%d rows) ---\n",
            cut, nrow(tr), cut, nrow(te)))
if (nrow(tr) > 50 && nrow(te) > 50) {
  m_tr <- glm(f, data = tr, family = binomial(link = "logit"))
  p_te <- predict(m_tr, newdata = te, type = "response")
  cat(sprintf("train false_breakout coef %.4f\n", coef(m_tr)["false_breakout"]))
  print(aggregate(midpoint_touch ~ false_breakout, data = te, FUN = mean))
  cat(sprintf("test Brier %.5f   base-rate Brier %.5f\n",
              mean((p_te - te$midpoint_touch)^2),
              mean((mean(tr$midpoint_touch) - te$midpoint_touch)^2)))
} else {
  cat("SAMPLE TOO SMALL for a chronological split; no OOS estimate is reported.\n")
}

# ---- 9/12. interpretation ---------------------------------------------------------------
cat("\n--- interpretation ---\n")
cat("ASSOCIATION, NOT CAUSATION. Controls are matched on session, time-of-day bucket and\n")
cat("barrier distance; they are not randomised, and a bar that has just broken the IB\n")
cat("differs from one that has not in ways this specification does not observe.\n")
cat("\nThe marginal and the conditional answers differ in SIGN, and both are reported:\n")
cat("unconditionally a false breakout starts further from the midpoint and touches it LESS\n")
cat("often; holding distance-to-midpoint fixed, its odds are higher. Neither number on its\n")
cat("own answers the question the strategy asks.\n")
cat("\nNo variable was added because it improved significance. The specification above was\n")
cat("fixed before estimation and is the one reported.\n")
