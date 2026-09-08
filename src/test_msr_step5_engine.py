"""
ST5 LIVE
MSR STEP 5 — C4 INTEGRATION TEST

Purpose:
    Validate that the production MSR Step 5 engine can be imported
    and executed correctly inside the ST5 LIVE repository.

This test does NOT optimize the strategy.
This test does NOT modify the engine.
"""

from pathlib import Path
import sys

import pandas as pd


# ============================================================
# PATH
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# ============================================================
# IMPORT C4 ENGINE
# ============================================================

try:
    from msr_step5_engine import (
        add_indicators,
        get_signal_count,
        law_is_alive,
        calculate_net_return,
        run_engine,
        summarize_trades,
        run_msr,
    )

    IMPORT_OK = True

except Exception as e:

    IMPORT_OK = False
    IMPORT_ERROR = e


# ============================================================
# TEST DATA
# ============================================================

DATA_CANDIDATES = [
    ROOT_DIR / "data" / "MSR.csv",
    ROOT_DIR / "data" / "MSR_STEP5.csv",
]


def find_msr_data():

    for path in DATA_CANDIDATES:

        if path.exists():

            return path

    return None


# ============================================================
# ASSERT HELPERS
# ============================================================

def check(
    name,
    condition,
    detail=""
):

    if condition:

        print(
            f"{name:<45}: PASS"
        )

        return True

    print(
        f"{name:<45}: FAIL"
    )

    if detail:

        print(
            f"    {detail}"
        )

    return False


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 80)
    print("ST5 LIVE — MSR STEP 5 C4 INTEGRATION TEST")
    print("=" * 80)
    print()

    failures = 0

    # ========================================================
    # 1. IMPORT
    # ========================================================

    print("[1] ENGINE IMPORT")

    if not IMPORT_OK:

        print(
            "ENGINE IMPORT                               : FAIL"
        )

        print(
            f"    {type(IMPORT_ERROR).__name__}: "
            f"{IMPORT_ERROR}"
        )

        print()
        print("C4 INTEGRATION TEST: FAIL")
        return 1

    print(
        "ENGINE IMPORT                               : PASS"
    )

    print()

    # ========================================================
    # 2. FIND DATA
    # ========================================================

    print("[2] TEST DATA")

    data_path = find_msr_data()

    if data_path is None:

        print(
            "MSR TEST DATA                               : FAIL"
        )

        print(
            "    Không tìm thấy MSR.csv trong data/"
        )

        print()
        print("C4 INTEGRATION TEST: FAIL")
        return 1

    print(
        "MSR TEST DATA                               : PASS"
    )

    print(
        f"    File: {data_path}"
    )

    print()

    # ========================================================
    # 3. LOAD DATA
    # ========================================================

    print("[3] DATA LOAD")

    try:

        df = pd.read_csv(
            data_path
        )

        required = [
            "Date",
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]

        missing = [
            col
            for col in required
            if col not in df.columns
        ]

        if missing:

            failures += 1

            check(
                "Required columns",
                False,
                f"Missing: {missing}"
            )

            print()
            print("C4 INTEGRATION TEST: FAIL")
            return 1

        check(
            "Required columns",
            True
        )

        check(
            "Rows > 100",
            len(df) > 100,
            f"rows={len(df)}"
        )

        print(
            f"    Rows: {len(df):,}"
        )

    except Exception as e:

        print(
            "DATA LOAD                                   : FAIL"
        )

        print(
            f"    {type(e).__name__}: {e}"
        )

        print()
        print("C4 INTEGRATION TEST: FAIL")
        return 1

    print()

    # ========================================================
    # 4. INDICATORS
    # ========================================================

    print("[4] INDICATOR ENGINE")

    try:

        data = add_indicators(
            df
        )

        indicator_columns = [
            "MACD",
            "MACD_SIGNAL",
            "MACD_HIST",
            "ROC10",
            "VOL_MA20",
            "VOLUME_RATIO",
            "ADX14",
            "ENTRY_SIGNAL",
        ]

        for col in indicator_columns:

            ok = check(
                f"Column {col}",
                col in data.columns
            )

            if not ok:
                failures += 1

        signal_count = get_signal_count(
            data
        )

        ok = check(
            "ENTRY_SIGNAL boolean",
            str(data["ENTRY_SIGNAL"].dtype)
            in ["bool", "boolean"]
        )

        if not ok:
            failures += 1

        print(
            f"    ENTRY signals: {signal_count:,}"
        )

    except Exception as e:

        print(
            "INDICATOR ENGINE                            : FAIL"
        )

        print(
            f"    {type(e).__name__}: {e}"
        )

        print()
        print("C4 INTEGRATION TEST: FAIL")
        return 1

    print()

    # ========================================================
    # 5. SIGNAL CONSISTENCY
    # ========================================================

    print("[5] SIGNAL CONSISTENCY")

    try:

        manual_signal = (
            (data["VOLUME_RATIO"] > 1)
            & (data["MACD_HIST"] > 0)
            & (data["ROC10"] > 2)
            & (data["ADX14"] > 30)
        )

        mismatch = int(
            (
                data["ENTRY_SIGNAL"]
                != manual_signal
            ).sum()
        )

        ok = check(
            "Manual signal matches C4",
            mismatch == 0,
            f"mismatch={mismatch}"
        )

        if not ok:
            failures += 1

        nan_signal = int(
            data.loc[
                data[
                    [
                        "VOLUME_RATIO",
                        "MACD_HIST",
                        "ROC10",
                        "ADX14",
                    ]
                ].isna().any(axis=1),
                "ENTRY_SIGNAL",
            ].sum()
        )

        ok = check(
            "No signal on indicator NaN",
            nan_signal == 0,
            f"nan_signals={nan_signal}"
        )

        if not ok:
            failures += 1

    except Exception as e:

        print(
            "SIGNAL CONSISTENCY                           : FAIL"
        )

        print(
            f"    {type(e).__name__}: {e}"
        )

        print()
        print("C4 INTEGRATION TEST: FAIL")
        return 1

    print()

    # ========================================================
    # 6. LAW CHECK
    # ========================================================

    print("[6] LAW CHECK")

    try:

        valid_rows = data[
            [
                "VOLUME_RATIO",
                "MACD_HIST",
                "ROC10",
                "ADX14",
            ]
        ].dropna()

        law_errors = 0

        for _, row in valid_rows.head(500).iterrows():

            expected = (
                (row["VOLUME_RATIO"] > 1)
                and (row["MACD_HIST"] > 0)
                and (row["ROC10"] > 2)
                and (row["ADX14"] > 30)
            )

            actual = law_is_alive(
                row
            )

            if expected != actual:

                law_errors += 1

        ok = check(
            "LAW logic consistency",
            law_errors == 0,
            f"errors={law_errors}"
        )

        if not ok:
            failures += 1

    except Exception as e:

        print(
            "LAW CHECK                                   : FAIL"
        )

        print(
            f"    {type(e).__name__}: {e}"
        )

        print()
        print("C4 INTEGRATION TEST: FAIL")
        return 1

    print()

    # ========================================================
    # 7. RETURN FUNCTION
    # ========================================================

    print("[7] RETURN ENGINE")

    try:

        ret = calculate_net_return(
            100.0,
            120.0
        )

        expected = (
            120.0 * (1 - 0.0015 - 0.0010)
        ) / (
            100.0 * (1 + 0.0015)
        ) - 1

        ok = check(
            "Net return formula",
            abs(ret - expected) < 1e-12,
            f"actual={ret}, expected={expected}"
        )

        if not ok:
            failures += 1

    except Exception as e:

        print(
            "RETURN ENGINE                               : FAIL"
        )

        print(
            f"    {type(e).__name__}: {e}"
        )

        print()
        print("C4 INTEGRATION TEST: FAIL")
        return 1

    print()

    # ========================================================
    # 8. TRADE ENGINE
    # ========================================================

    print("[8] TRADE ENGINE")

    try:

        engine_data, trades = run_engine(
            df
        )

        ok = check(
            "Engine returned dataframe",
            isinstance(
                engine_data,
                pd.DataFrame
            )
        )

        if not ok:
            failures += 1

        ok = check(
            "Trades returned dataframe",
            isinstance(
                trades,
                pd.DataFrame
            )
        )

        if not ok:
            failures += 1

        trade_columns = [
            "TradeID",
            "EntryIndex",
            "ExitIndex",
            "EntryDate",
            "ExitDate",
            "EntryPrice",
            "ExitPrice",
            "HoldBars",
            "TargetPrice",
            "ExitReason",
            "NetReturnPct",
        ]

        for col in trade_columns:

            ok = check(
                f"Trade column {col}",
                col in trades.columns
            )

            if not ok:
                failures += 1

        print(
            f"    Trades: {len(trades):,}"
        )

    except Exception as e:

        print(
            "TRADE ENGINE                                : FAIL"
        )

        print(
            f"    {type(e).__name__}: {e}"
        )

        print()
        print("C4 INTEGRATION TEST: FAIL")
        return 1

    print()

    # ========================================================
    # 9. TRADE INTEGRITY
    # ========================================================

    print("[9] TRADE INTEGRITY")

    try:

        if not trades.empty:

            unique_ids = (
                trades["TradeID"].is_unique
            )

            sequential_ids = (
                trades["TradeID"].tolist()
                == list(
                    range(
                        1,
                        len(trades) + 1
                    )
                )
            )

            no_overlap = True

            previous_exit = -1

            for _, trade in trades.iterrows():

                entry = int(
                    trade["EntryIndex"]
                )

                exit_ = int(
                    trade["ExitIndex"]
                )

                if entry <= previous_exit:

                    no_overlap = False

                if exit_ < entry:

                    no_overlap = False

                previous_exit = exit_

            checks = [
                (
                    "Trade IDs unique",
                    unique_ids
                ),
                (
                    "Trade IDs sequential",
                    sequential_ids
                ),
                (
                    "No overlapping trades",
                    no_overlap
                ),
            ]

            for name, result in checks:

                ok = check(
                    name,
                    result
                )

                if not ok:
                    failures += 1

        else:

            print(
                "No trades generated."
            )

    except Exception as e:

        print(
            "TRADE INTEGRITY                            : FAIL"
        )

        print(
            f"    {type(e).__name__}: {e}"
        )

        print()
        print("C4 INTEGRATION TEST: FAIL")
        return 1

    print()

    # ========================================================
    # 10. PUBLIC API
    # ========================================================

    print("[10] PUBLIC API")

    try:

        result = run_msr(
            df
        )

        required_keys = [
            "data",
            "trades",
            "summary",
        ]

        for key in required_keys:

            ok = check(
                f"run_msr() key: {key}",
                key in result
            )

            if not ok:
                failures += 1

        ok = check(
            "run_msr() data",
            isinstance(
                result["data"],
                pd.DataFrame
            )
        )

        if not ok:
            failures += 1

        ok = check(
            "run_msr() trades",
            isinstance(
                result["trades"],
                pd.DataFrame
            )
        )

        if not ok:
            failures += 1

        ok = check(
            "run_msr() summary",
            isinstance(
                result["summary"],
                dict
            )
        )

        if not ok:
            failures += 1

    except Exception as e:

        print(
            "PUBLIC API                                  : FAIL"
        )

        print(
            f"    {type(e).__name__}: {e}"
        )

        print()
        print("C4 INTEGRATION TEST: FAIL")
        return 1

    # ========================================================
    # FINAL
    # ========================================================

    print()
    print("=" * 80)

    if failures == 0:

        print(
            "C4 INTEGRATION TEST: PASS"
        )

        print(
            "MSR Step 5 engine is executable inside ST5 LIVE."
        )

        print("=" * 80)

        return 0

    print(
        f"C4 INTEGRATION TEST: FAIL "
        f"({failures} checks)"
    )

    print("=" * 80)

    return 1


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
