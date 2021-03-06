import pandas as pd

from lusidtools.lpt import lpt
from lusidtools.lpt import lse
from lusidtools.lpt import stdargs

# Instrument column names
NAME = "name"
LT_SCOPE = "look_through_portfolio_id.scope"
LT_CODE = "look_through_portfolio_id.code"
TOOLNAME = "instr_create"
TOOLTIP = "Create Instruments"


def parse(extend=None, args=None):
    return (
        stdargs.Parser("Upsert Instruments", ["filename", "limit", "test"])
        .add("input", nargs="+")
        .add(
            "--mappings",
            nargs="+",
            help="column name mappings of the form TICKER=col1 etc",
        )
        .add(
            "--identifiers",
            nargs="+",
            default=["ClientInternal", "Figi"],
            help="Identifier types provided",
        )
        .extend(extend)
        .parse(args)
    )


def process_args(api, args):
    aliases = {
        "CINT": "ClientInternal",
        "FIGI": "Figi",
        "RIC": "P:Instrument/default/RIC",
        "TICKER": "P:Instrument/default/Ticker",
        "ISIN": "P:Instrument/default/Isin",
    }

    if args.input:
        df = pd.concat(
            [lpt.read_input(input_file, dtype=str) for input_file in args.input],
            ignore_index=True,
            sort=False,
        )

        if args.mappings:
            df.rename(
                columns=dict(
                    [
                        (s[1], aliases.get(s[0], s[0]))
                        for s in [m.split("=") for m in args.mappings]
                    ]
                ),
                inplace=True,
            )

        prop_keys = [col for col in df.columns.values if col.startswith("P:")]

        identifiers = [col for col in df.columns.values if col in args.identifiers]

        # Identifiers have to be unique
        df = df.drop_duplicates(identifiers)

        def make_identifiers(row):
            return {
                identifier: api.models.InstrumentIdValue(row[identifier])
                for identifier in identifiers
                if pd.notna(row[identifier])
            }

        def make_properties(row):
            return [
                api.models.ModelProperty(key[2:], api.models.PropertyValue(row[key]))
                for key in prop_keys
                if pd.notna(row[key])
            ]

        def success(r):
            df = lpt.to_df(
                [err[1] for err in r.content.failed.items()], ["id", "detail"]
            )
            df.columns = ["FAILED-INSTRUMENT", "ERROR"]
            return lpt.trim_df(df, args.limit, sort="FAILED-INSTRUMENT")

        has_lookthrough = LT_SCOPE in df.columns.values

        requests = [
            api.models.InstrumentDefinition(
                row["name"],
                make_identifiers(row),
                make_properties(row),
                api.models.ResourceId(row[LT_SCOPE], row[LT_CODE])
                if (has_lookthrough and pd.notna(row[LT_SCOPE]))
                else None,
            )
            for idx, row in df.iterrows()
        ]

        # Convert valid requests to dictionary
        def make_key(r):
            sec_id = list(r.identifiers.items())[0]
            return "{}:{}".format(sec_id[0], sec_id[1].value)

        requests = {make_key(r): r for r in requests if len(r.identifiers.keys()) > 0}

        if args.test:
            lpt.display_df(df[identifiers + prop_keys + ["name"]])
            print(requests)
            exit()

        return api.call.upsert_instruments(instruments=requests).bind(success)


def main():
    lpt.standard_flow(parse, lse.connect, process_args)
