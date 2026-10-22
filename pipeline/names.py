"""Matching the names other organisations use for a council to its ONS code.

The Ombudsman, the Regulator of Social Housing and Silktide name councils
("London Borough of Lewisham", "Wigan Metropolitan Borough Council")
rather than giving an ONS code, so names are reduced to a key ("lewisham",
"wigan") and matched on that.
"""

import re
import unicodedata

# Words that say what kind of council it is, not which one
_NOISE = [
    r"\bthe\b", r"\blondon borough of\b", r"\broyal borough of\b", r"\bcity of\b", r"\bcounty of\b",
    r"\bborough of\b", r"\bmetropolitan borough council\b", r"\bmetropolitan district council\b",
    r"\bmetropolitan borough\b", r"\bborough council\b", r"\bcity council\b", r"\bcounty council\b",
    r"\bdistrict council\b", r"\bcouncil\b", r"\blondon borough\b", r"\bunitary authority\b",
    r"\bcounty borough\b", r"\bmbc\b", r"\bltd\b", r"\blimited\b",
    # Left over from names in an unusual order ("Haringey London Borough Council")
    r"\blondon\b", r"\broyal\b", r"\bborough\b", r"\bmetropolitan\b", r"\bdistrict\b", r"\bcity\b",
    r"\bcounty\b",
]

# Names that reduce to something different from the ONS name's key
ALIASES = {
    "bristol": "bristolcityof",
    "herefordshire": "herefordshirecountyof",
    "kingstonuponhull": "kingstonuponhullcityof",
    "hull": "kingstonuponhullcityof",
    "durham": "countydurham",
    "bournemouthchristchurchpoole": "bournemouthchristchurchandpoole",
    "bcp": "bournemouthchristchurchandpoole",
    "stalbans": "stalbans",
    "southendonsea": "southendonsea",
    "hammersmithfulham": "hammersmithandfulham",
    "kensingtonchelsea": "kensingtonandchelsea",
    "barkingdagenham": "barkinganddagenham",
    "brightonhove": "brightonandhove",
    "windsormaidenhead": "windsorandmaidenhead",
    "telfordwrekin": "telfordandwrekin",
    "bathnortheastsomerset": "bathandnortheastsomerset",
    "banes": "bathandnortheastsomerset",
    "redcarcleveland": "redcarandcleveland",
    "stockton": "stocktonontees",
    "newcastle": "newcastleupontyne",
    "kingston": "kingstonuponthames",
    "richmond": "richmonduponthames",
    "stokeontrent": "stokeontrent",
    "eastridingofyorkshire": "eastridingofyorkshire",
    "eastriding": "eastridingofyorkshire",
    "westminster": "westminster",
    "cityofwestminster": "westminster",
    "cityoflondon": "cityoflondon",
    # Scotland
    "edinburgh": "cityofedinburgh",
    "eileansiar": "naheileanansiar",
    "comhairlenaneileansiar": "naheileanansiar",
    "westernisles": "naheileanansiar",
    "orkney": "orkneyislands",
    "shetland": "shetlandislands",
}


def key(name):
    """ "London Borough of Lewisham" -> "lewisham"; "St. Helens" -> "sthelens"."""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"\(.*?\)", " ", text)
    for pattern in _NOISE:
        text = re.sub(pattern, " ", text)
    text = re.sub(r"[^a-z]", "", text)
    return ALIASES.get(text, text)


def ons_key(name):
    """The key for an ONS name ("Bristol, City of" -> "bristolcityof")."""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z]", "", text.replace("&", "and"))
    return text


class Matcher:
    """Finds the ONS code for a name, given {code: ONS name}."""

    def __init__(self, councils):
        self.by_key = {}
        for code, name in councils.items():
            self.by_key[ons_key(name)] = code
            self.by_key.setdefault(key(name), code)

    def code(self, name):
        k = key(name)
        if k in self.by_key:
            return self.by_key[k]
        # "and" is sometimes dropped or added
        alt = k.replace("and", "")
        for candidate, code in self.by_key.items():
            if candidate.replace("and", "") == alt:
                return code
        return None
