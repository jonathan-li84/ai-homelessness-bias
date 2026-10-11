#!/usr/bin/env python3
"""Request independent Gemini PIT estimates and print each response to stdout.

Uses GEMINI_API_KEY rather than storing credentials in source. Run numbers
identify attempted requests; failed requests do not count as completed responses.
"""

from __future__ import annotations

import argparse
import os
import time

from google import genai


PROMPT = """Estimate the January 2024 Point-in-Time (PIT) homelessness total for each California Continuum of Care (CoC) listed below.

Each estimate must include sheltered and unsheltered people across the entire CoC’s geographic area, not just its principal city.

Use your existing knowledge and reasoning to assess each CoC individually. Do not browse the web, use external tools, access files, or ask follow-up questions.

Provide one specific whole-number estimate for each CoC. Select the number you judge most likely to match its January 2024 PIT total. If uncertain, still provide your single best numerical estimate.

Do not provide ranges, qualifications such as “about,” or explanatory text. Do not constrain your estimates to match a statewide total.

Return only CSV with these columns:

coc_number,coc_name,estimated_pit_total_2024

Include exactly one row per CoC, in the order listed. Preserve the IDs and names, enclose names in double quotes, and write estimates as nonnegative integers without thousands separators.

CA-500,"San Jose/Santa Clara City & County CoC"
CA-501,"San Francisco CoC"
CA-502,"Oakland, Berkeley/Alameda County CoC"
CA-503,"Sacramento City & County CoC"
CA-504,"Santa Rosa, Petaluma/Sonoma County CoC"
CA-505,"Contra Costa County CoC"
CA-506,"Salinas/Monterey, San Benito Counties CoC"
CA-507,"Marin County CoC"
CA-508,"Watsonville/Santa Cruz City & County CoC"
CA-509,"Mendocino County CoC"
CA-510,"Turlock, Modesto/Stanislaus County CoC"
CA-511,"Stockton/San Joaquin County CoC"
CA-512,"Daly City/San Mateo County CoC"
CA-513,"Visalia/Kings, Tulare Counties CoC"
CA-514,"Fresno City & County/Madera County CoC"
CA-515,"Roseville, Rocklin/Placer County CoC"
CA-516,"Redding/Shasta, Siskiyou, Lassen, Plumas, Del Norte, Modoc, Sierra Counties CoC"
CA-517,"Napa City & County CoC"
CA-518,"Vallejo/Solano County CoC"
CA-519,"Chico, Paradise/Butte County CoC"
CA-520,"Merced City & County CoC"
CA-521,"Davis, Woodland/Yolo County CoC"
CA-522,"Humboldt County CoC"
CA-523,"Colusa, Glenn, Trinity Counties CoC"
CA-524,"Yuba City & County/Sutter County CoC"
CA-525,"El Dorado County CoC"
CA-526,"Amador, Calaveras, Mariposa, Tuolumne Counties CoC"
CA-527,"Tehama County CoC"
CA-529,"Lake County CoC"
CA-530,"Alpine, Inyo, Mono Counties CoC"
CA-531,"Nevada County CoC"
CA-600,"Los Angeles City & County CoC"
CA-601,"San Diego City and County CoC"
CA-602,"Santa Ana, Anaheim/Orange County CoC"
CA-603,"Santa Maria/Santa Barbara County CoC"
CA-604,"Bakersfield/Kern County CoC"
CA-606,"Long Beach CoC"
CA-607,"Pasadena CoC"
CA-608,"Riverside City & County CoC"
CA-609,"San Bernardino City & County CoC"
CA-611,"Oxnard, San Buenaventura/Ventura County CoC"
CA-612,"Glendale CoC"
CA-613,"Imperial County CoC"
CA-614,"San Luis Obispo County CoC"
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gemini-3.8-flash")
    parser.add_argument("--runs", type=int, default=50, help="Number of attempted requests.")
    parser.add_argument("--delay-seconds", type=float, default=12)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    if args.delay_seconds < 0:
        parser.error("--delay-seconds must be nonnegative")
    return args


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("Set GEMINI_API_KEY before requesting estimates.")

    successful_runs = 0
    with genai.Client(api_key=api_key) as client:
        for run in range(1, args.runs + 1):
            print(f"=== Run {run} of {args.runs} ===", flush=True)
            try:
                # Each request contains only the fixed prompt, with no chat history.
                response = client.models.generate_content(
                    model=args.model,
                    contents=PROMPT,
                )
                if not response.text or not response.text.strip():
                    raise ValueError("The model returned no text.")
                print(response.text, flush=True)
                successful_runs += 1
            except Exception as error:
                print(f"Error during run {run}: {error}", flush=True)

            if run < args.runs:
                print(f"Sleeping for {args.delay_seconds:g} seconds between requests...\n", flush=True)
                time.sleep(args.delay_seconds)

    print(f"\nFinished: {successful_runs} text responses, {args.runs - successful_runs} failed requests.", flush=True)


if __name__ == "__main__":
    main()
