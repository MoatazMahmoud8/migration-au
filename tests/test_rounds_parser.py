import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from rounds_parser import parse_current_round


HTML = """
<h3>Invitations issued on 4 June 2026</h3>
<table>
  <tr><th>Visa subclass</th><th>Total EOIs Invited</th><th>Tie break date - month and year</th></tr>
  <tr><td>Skilled Independent visa (subclass 189)</td><td>10,000</td><td>24/04/2026</td></tr>
</table>
<table>
  <tr><th>Visa subclass</th><th>Jul</th><th>Aug</th><th>Nov</th><th>Jun</th></tr>
  <tr><td>Skilled Independent visa (subclass 189)</td><td>0</td><td>6,887</td><td>10,000</td><td>10,000</td></tr>
  <tr><td>Skilled Work Regional (Provisional) visa (subclass 491) - Family Sponsored</td><td>0</td><td>150</td><td>300</td><td>0</td></tr>
</table>
"""


class CurrentRoundParserTests(unittest.TestCase):
    def test_uses_matching_month_when_subclass_missing_from_summary(self):
        escaped_html = HTML.replace("<th>Jun</th>", "<th>\\t Jun \\t</th>")
        result = parse_current_round(escaped_html)

        self.assertEqual(result["date"], "2026-06-04")
        self.assertEqual(result["sc189Total"], 10_000)
        self.assertEqual(result["sc189TieBreak"], "2026-04")
        self.assertEqual(result["sc491FamilyTotal"], 0)
        self.assertIsNone(result["sc491FamilyTieBreak"])

    def test_rejects_summary_and_monthly_mismatch(self):
        mismatched = HTML.replace("<td>10,000</td><td>10,000</td></tr>", "<td>10,000</td><td>9,999</td></tr>")

        with self.assertRaisesRegex(ValueError, "does not match"):
            parse_current_round(mismatched)


if __name__ == "__main__":
    unittest.main()