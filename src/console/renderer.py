"""ANSI-coloured console table for email analysis results."""

CATEGORY_COLORS = {
    "Support": "\033[96m",  # cyan
    "Sales": "\033[93m",  # yellow
    "Spam": "\033[91m",  # red
    "Internal": "\033[92m",  # green
    "Finance": "\033[95m",  # magenta
    "Legal": "\033[94m",  # blue
    "Other": "\033[97m",  # white
}
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

PRIORITY_COLORS = {
    "HIGH": "\033[91m",  # red
    "MEDIUM": "\033[93m",  # yellow
    "LOW": "\033[92m",  # green
}


class EmailTableRenderer:
    COL_WIDTHS = {"category": 10, "sender": 24, "date": 12, "subject": 34}

    def render(
        self,
        rows: list[list[str]],
        results: list[tuple[str, str, str, str] | None],
        sender_i: int,
        date_i: int,
        subject_i: int,
    ) -> None:
        self._print_header()
        for idx, (row, result) in enumerate(zip(rows, results), start=1):
            self._print_row(idx, row, result, sender_i, date_i, subject_i)

    def _print_header(self) -> None:
        w = self.COL_WIDTHS
        header_line = (
            f"{'#':<5}"
            f"{'Category':<{w['category']}}  "
            f"{'Sender':<{w['sender']}}  "
            f"{'Date':<{w['date']}}  "
            f"{'Subject':<{w['subject']}}"
        )
        sep_width = sum(w.values()) + len(w) * 3 + 2
        print(f"\n{BOLD}{header_line}{RESET}")
        print("\u2500" * sep_width)

    def _print_row(
        self,
        idx: int,
        row: list[str],
        result: tuple[str, str, str, str] | None,
        sender_i: int,
        date_i: int,
        subject_i: int,
    ) -> None:
        w = self.COL_WIDTHS
        sender = row[sender_i][: w["sender"]]
        date = row[date_i][: w["date"]]
        subject = row[subject_i][: w["subject"]]
        indent = "      "

        if result is None:
            print(
                f"{DIM}{idx:<5}"
                f"{'—':<{w['category']}}  "
                f"{sender:<{w['sender']}}  "
                f"{date:<{w['date']}}  "
                f"{subject:<{w['subject']}}"
                f"  (already processed){RESET}"
            )
            print()
            return

        summary, category, action_items, reply_strategy = result
        color = CATEGORY_COLORS.get(category, RESET)

        print(
            f"{idx:<5}"
            f"{color}{category:<{w['category']}}{RESET}  "
            f"{sender:<{w['sender']}}  "
            f"{date:<{w['date']}}  "
            f"{subject:<{w['subject']}}"
        )
        print(f"{indent}{DIM}\u2192 {summary}{RESET}")

        if action_items:
            print(f"{indent}{BOLD}Action Items:{RESET}")
            for line in action_items.splitlines():
                line = line.strip()
                if line:
                    print(f"{indent}  {self._color_priority_line(line)}")

        if reply_strategy:
            print(f"{indent}{BOLD}Reply Strategy:{RESET}")
            for line in reply_strategy.splitlines():
                line = line.strip()
                if line:
                    print(f"{indent}  {DIM}{line}{RESET}")

        print()

    @staticmethod
    def _color_priority_line(line: str) -> str:
        """Wrap the [PRIORITY] tag in its ANSI color."""
        for priority, color in PRIORITY_COLORS.items():
            tag = f"[{priority}]"
            if tag in line:
                return line.replace(tag, f"{color}{BOLD}{tag}{RESET}", 1)
        return line
