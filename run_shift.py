"""
Runs scanner_in.py and institutional_scanner_in.py concurrently, in one
process, for one shift of the trading day. GitHub Actions jobs are capped at
6 hours, and the full NSE session (9:15 AM-3:30 PM IST, 6h15m) is close
enough to that cap that it's split into two shifts for safety margin (see
.github/workflows/) -- this script launches both bots for whichever shift
it's called for and waits for both to finish.

Not meant to be run outside of the shift workflows -- for local testing,
just run scanner_in.py or institutional_scanner_in.py directly.
"""

import logging
import sys
import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def run_scanner():
    from scanner_in import INSwingScanner
    try:
        INSwingScanner().run_scanner_loop()
    except Exception:
        logging.exception("scanner_in crashed")


def run_institutional():
    from institutional_scanner_in import InstitutionalFlowScannerIN
    try:
        InstitutionalFlowScannerIN().run_scanner_loop()
    except Exception:
        logging.exception("institutional_scanner_in crashed")


if __name__ == "__main__":
    t1 = threading.Thread(target=run_scanner, name="scanner_in")
    t2 = threading.Thread(target=run_institutional, name="institutional_scanner_in")

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    logging.info("Both scanners finished this shift.")
    sys.exit(0)
