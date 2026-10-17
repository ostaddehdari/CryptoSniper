import csv
import io
from numbers import Number
from xml.sax.saxutils import escape


def safe_csv_cell(value):
    if isinstance(value, Number):
        return str(value)
    text = str(value)
    stripped = text.lstrip()
    if stripped.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def csv_bytes(dataset):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(
        [
            "period",
            "group",
            "currency",
            "trades",
            "wins",
            "losses",
            "breakeven",
            "unknown",
            "gross_realized",
            "fees",
            "margin_interest",
            "net_realized",
        ]
    )
    for row in dataset["rows"]:
        writer.writerow(
            map(
                safe_csv_cell,
                [
                    row.period_start,
                    row.dimension_value,
                    row.currency,
                    row.trade_count,
                    row.wins,
                    row.losses,
                    row.breakeven,
                    row.unknown_count,
                    row.gross_realized,
                    row.fees,
                    row.margin_interest,
                    row.net_realized,
                ],
            )
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def svg_bytes(dataset):
    rows = dataset["rows"][:60]
    width, row_height = 1000, 34
    height = max(180, 90 + len(rows) * row_height)
    maximum = max((abs(row.net_realized) for row in rows), default=0)
    content = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f7faf9"/>',
        "<style>text{font-family:Arial,sans-serif;fill:#16312e}.muted{fill:#607672}.pos{fill:#087f73}.neg{fill:#bf3d4a}</style>",
        '<text x="950" y="40" text-anchor="end" font-size="24">CryptoSniper Performance</text>',
    ]
    for index, row in enumerate(rows):
        y = 78 + index * row_height
        value = float(abs(row.net_realized) / maximum) * 600 if maximum else 0
        css = "pos" if row.net_realized >= 0 else "neg"
        label = escape(f"{row.period_start} · {row.dimension_value} · {row.currency}")
        amount = escape(str(row.net_realized))
        content.extend(
            [
                '<text class="muted" x="950" '
                f'y="{y + 16}" text-anchor="end" font-size="13">{label}</text>',
                f'<rect class="{css}" x="120" y="{y}" width="{value:.2f}" height="19" rx="5"/>',
                f'<text x="108" y="{y + 15}" text-anchor="end" font-size="12">{amount}</text>',
            ]
        )
    content.append("</svg>")
    return "".join(content).encode()
