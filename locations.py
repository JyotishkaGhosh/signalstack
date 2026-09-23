"""Turn messy job locations into city, state, country and remote / hybrid / on-site.

Used by transform.py. Sources send anything from "Bengaluru, Karnataka, India" to
"Remote - US", "SF, NYC" or just a country code, so this uses small lookup tables
for countries, states and common cities, and keeps unknown place names as they are.
"""
import re

COUNTRIES = {
    "India": ["in", "ind", "india", "bharat"],
    "United States": ["us", "usa", "u.s.", "u.s.a.", "united states", "united states of america", "america"],
    "United Kingdom": ["uk", "gb", "gbr", "u.k.", "united kingdom", "great britain", "britain", "england", "scotland", "wales", "northern ireland"],
    "Canada": ["ca", "can", "canada"],
    "Germany": ["de", "deu", "germany", "deutschland"],
    "France": ["fr", "fra", "france"],
    "Netherlands": ["nl", "nld", "netherlands", "the netherlands", "holland"],
    "Ireland": ["ie", "irl", "ireland"],
    "Spain": ["es", "esp", "spain", "españa"],
    "Portugal": ["pt", "prt", "portugal"],
    "Italy": ["it", "ita", "italy", "italia"],
    "Poland": ["pl", "pol", "poland", "polska"],
    "Sweden": ["se", "swe", "sweden"],
    "Denmark": ["dk", "dnk", "denmark"],
    "Norway": ["no", "nor", "norway"],
    "Finland": ["fi", "fin", "finland"],
    "Switzerland": ["ch", "che", "switzerland", "schweiz"],
    "Austria": ["at", "aut", "austria", "österreich"],
    "Belgium": ["be", "bel", "belgium"],
    "Czechia": ["cz", "cze", "czechia", "czech republic"],
    "Greece": ["gr", "grc", "greece"],
    "Romania": ["ro", "rou", "romania"],
    "Bulgaria": ["bg", "bgr", "bulgaria"],
    "Hungary": ["hu", "hun", "hungary"],
    "Serbia": ["rs", "srb", "serbia"],
    "Ukraine": ["ua", "ukr", "ukraine"],
    "Lithuania": ["lt", "ltu", "lithuania"],
    "Latvia": ["lv", "lva", "latvia"],
    "Estonia": ["ee", "est", "estonia"],
    "Croatia": ["hr", "hrv", "croatia"],
    "Luxembourg": ["lu", "lux", "luxembourg"],
    "Türkiye": ["tr", "tur", "turkey", "türkiye", "turkiye"],
    "Israel": ["il", "isr", "israel"],
    "United Arab Emirates": ["ae", "are", "uae", "united arab emirates"],
    "Saudi Arabia": ["sa", "sau", "saudi arabia", "ksa"],
    "Egypt": ["eg", "egy", "egypt"],
    "South Africa": ["za", "zaf", "south africa"],
    "Nigeria": ["ng", "nga", "nigeria"],
    "Kenya": ["ke", "ken", "kenya"],
    "Singapore": ["sg", "sgp", "singapore"],
    "Japan": ["jp", "jpn", "japan"],
    "South Korea": ["kr", "kor", "south korea", "korea", "republic of korea"],
    "China": ["cn", "chn", "china"],
    "Hong Kong": ["hk", "hkg", "hong kong", "hong kong sar"],
    "Taiwan": ["tw", "twn", "taiwan"],
    "Australia": ["au", "aus", "australia"],
    "New Zealand": ["nz", "nzl", "new zealand"],
    "Indonesia": ["id", "idn", "indonesia"],
    "Malaysia": ["my", "mys", "malaysia"],
    "Philippines": ["ph", "phl", "philippines"],
    "Thailand": ["th", "tha", "thailand"],
    "Vietnam": ["vn", "vnm", "vietnam", "viet nam"],
    "Pakistan": ["pk", "pak", "pakistan"],
    "Bangladesh": ["bd", "bgd", "bangladesh"],
    "Sri Lanka": ["lk", "lka", "sri lanka"],
    "Nepal": ["np", "npl", "nepal"],
    "Brazil": ["br", "bra", "brazil", "brasil"],
    "Mexico": ["mx", "mex", "mexico", "méxico"],
    "Argentina": ["ar", "arg", "argentina"],
    "Chile": ["cl", "chl", "chile"],
    "Colombia": ["co", "col", "colombia"],
    "Peru": ["pe", "per", "peru"],
    "Costa Rica": ["cr", "cri", "costa rica"],
    "Uruguay": ["uy", "ury", "uruguay"],
}
COUNTRY = {alias: name for name, aliases in COUNTRIES.items() for alias in aliases}
# Short codes are only trusted when they are written in capitals ("IN", "US"), since
# "in", "no" and "it" are also ordinary words
SHORT_CODES = {a for a in COUNTRY if len(a) <= 3 and a.isalpha()}

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
IN_STATE_CODES = {"KA": "Karnataka", "MH": "Maharashtra", "TN": "Tamil Nadu", "TS": "Telangana", "TG": "Telangana",
                  "DL": "Delhi", "HR": "Haryana", "UP": "Uttar Pradesh", "WB": "West Bengal", "GJ": "Gujarat",
                  "KL": "Kerala", "RJ": "Rajasthan", "AP": "Andhra Pradesh", "PB": "Punjab", "OR": "Odisha"}
CA_PROVINCES = {"ON": "Ontario", "BC": "British Columbia", "QC": "Quebec", "AB": "Alberta", "MB": "Manitoba",
                "NS": "Nova Scotia", "SK": "Saskatchewan", "NB": "New Brunswick"}
IN_STATES = ["Andhra Pradesh", "Assam", "Bihar", "Chhattisgarh", "Delhi", "Goa", "Gujarat", "Haryana",
             "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Odisha",
             "Punjab", "Rajasthan", "Tamil Nadu", "Telangana", "Uttar Pradesh", "Uttarakhand", "West Bengal",
             "Chandigarh", "Jammu and Kashmir"]
AU_STATES = ["New South Wales", "Victoria", "Queensland", "Western Australia", "South Australia", "Tasmania"]

STATE = {}                                   # lowercase name -> (state, country)
for code, name in US_STATES.items():
    STATE[name.lower()] = (name, "United States")
for code, name in CA_PROVINCES.items():
    STATE[name.lower()] = (name, "Canada")
for name in IN_STATES:
    STATE[name.lower()] = (name, "India")
for name in AU_STATES:
    STATE[name.lower()] = (name, "Australia")
STATE["new delhi"] = ("Delhi", "India")
STATE["nct of delhi"] = ("Delhi", "India")
STATE["orissa"] = ("Odisha", "India")
STATE["ncr"] = ("Delhi", "India")
STATE["delhi ncr"] = ("Delhi", "India")

# City aliases -> (city, state, country)
_CITIES = [
    # India
    ("Bengaluru", "Karnataka", "India", ["bengaluru", "bangalore", "bengaluru urban", "blr"]),
    ("Mumbai", "Maharashtra", "India", ["mumbai", "bombay", "navi mumbai", "thane"]),
    ("Pune", "Maharashtra", "India", ["pune"]),
    ("Nagpur", "Maharashtra", "India", ["nagpur"]),
    ("New Delhi", "Delhi", "India", ["new delhi", "delhi", "delhi ncr", "ncr"]),
    ("Gurugram", "Haryana", "India", ["gurugram", "gurgaon"]),
    ("Noida", "Uttar Pradesh", "India", ["noida", "greater noida"]),
    ("Hyderabad", "Telangana", "India", ["hyderabad", "secunderabad"]),
    ("Chennai", "Tamil Nadu", "India", ["chennai", "madras"]),
    ("Coimbatore", "Tamil Nadu", "India", ["coimbatore"]),
    ("Kolkata", "West Bengal", "India", ["kolkata", "calcutta"]),
    ("Ahmedabad", "Gujarat", "India", ["ahmedabad"]),
    ("Vadodara", "Gujarat", "India", ["vadodara", "baroda"]),
    ("Jaipur", "Rajasthan", "India", ["jaipur"]),
    ("Kochi", "Kerala", "India", ["kochi", "cochin"]),
    ("Thiruvananthapuram", "Kerala", "India", ["thiruvananthapuram", "trivandrum"]),
    ("Chandigarh", "Chandigarh", "India", ["chandigarh", "mohali"]),
    ("Indore", "Madhya Pradesh", "India", ["indore"]),
    ("Mysuru", "Karnataka", "India", ["mysuru", "mysore"]),
    ("Bhubaneswar", "Odisha", "India", ["bhubaneswar"]),
    ("Lucknow", "Uttar Pradesh", "India", ["lucknow"]),
    ("Visakhapatnam", "Andhra Pradesh", "India", ["visakhapatnam", "vizag"]),
    # United States
    ("San Francisco", "California", "United States", ["san francisco", "sf", "san francisco bay area", "bay area", "sf bay area"]),
    ("South San Francisco", "California", "United States", ["south san francisco"]),
    ("San Jose", "California", "United States", ["san jose"]),
    ("Mountain View", "California", "United States", ["mountain view"]),
    ("Palo Alto", "California", "United States", ["palo alto"]),
    ("Menlo Park", "California", "United States", ["menlo park"]),
    ("Sunnyvale", "California", "United States", ["sunnyvale"]),
    ("Santa Clara", "California", "United States", ["santa clara"]),
    ("Redwood City", "California", "United States", ["redwood city"]),
    ("San Mateo", "California", "United States", ["san mateo"]),
    ("Oakland", "California", "United States", ["oakland"]),
    ("Los Angeles", "California", "United States", ["los angeles", "la"]),
    ("San Diego", "California", "United States", ["san diego"]),
    ("Irvine", "California", "United States", ["irvine"]),
    ("Seattle", "Washington", "United States", ["seattle"]),
    ("Bellevue", "Washington", "United States", ["bellevue"]),
    ("Redmond", "Washington", "United States", ["redmond"]),
    ("Portland", "Oregon", "United States", ["portland"]),
    ("New York", "New York", "United States", ["new york", "new york city", "nyc", "ny", "manhattan", "brooklyn"]),
    ("Boston", "Massachusetts", "United States", ["boston"]),
    ("Cambridge", "Massachusetts", "United States", ["cambridge, ma"]),
    ("Chicago", "Illinois", "United States", ["chicago"]),
    ("Austin", "Texas", "United States", ["austin"]),
    ("Dallas", "Texas", "United States", ["dallas"]),
    ("Houston", "Texas", "United States", ["houston"]),
    ("Denver", "Colorado", "United States", ["denver"]),
    ("Boulder", "Colorado", "United States", ["boulder"]),
    ("Atlanta", "Georgia", "United States", ["atlanta"]),
    ("Miami", "Florida", "United States", ["miami"]),
    ("Washington", "District of Columbia", "United States", ["washington, dc", "washington dc", "washington d.c.", "dc"]),
    ("Arlington", "Virginia", "United States", ["arlington"]),
    ("Philadelphia", "Pennsylvania", "United States", ["philadelphia"]),
    ("Pittsburgh", "Pennsylvania", "United States", ["pittsburgh"]),
    ("Salt Lake City", "Utah", "United States", ["salt lake city"]),
    ("Phoenix", "Arizona", "United States", ["phoenix"]),
    ("Minneapolis", "Minnesota", "United States", ["minneapolis"]),
    ("Detroit", "Michigan", "United States", ["detroit"]),
    ("Nashville", "Tennessee", "United States", ["nashville"]),
    ("Raleigh", "North Carolina", "United States", ["raleigh"]),
    ("Charlotte", "North Carolina", "United States", ["charlotte"]),
    ("Columbus", "Ohio", "United States", ["columbus"]),
    # Canada
    ("Toronto", "Ontario", "Canada", ["toronto"]),
    ("Vancouver", "British Columbia", "Canada", ["vancouver"]),
    ("Montreal", "Quebec", "Canada", ["montreal", "montréal"]),
    ("Ottawa", "Ontario", "Canada", ["ottawa"]),
    ("Waterloo", "Ontario", "Canada", ["waterloo"]),
    ("Calgary", "Alberta", "Canada", ["calgary"]),
    # Europe
    ("London", "England", "United Kingdom", ["london"]),
    ("Manchester", "England", "United Kingdom", ["manchester"]),
    ("Edinburgh", "Scotland", "United Kingdom", ["edinburgh"]),
    ("Dublin", None, "Ireland", ["dublin"]),
    ("Berlin", "Berlin", "Germany", ["berlin"]),
    ("Munich", "Bavaria", "Germany", ["munich", "münchen", "muenchen"]),
    ("Hamburg", "Hamburg", "Germany", ["hamburg"]),
    ("Frankfurt", "Hesse", "Germany", ["frankfurt", "frankfurt am main"]),
    ("Cologne", "North Rhine-Westphalia", "Germany", ["cologne", "köln", "koeln"]),
    ("Düsseldorf", "North Rhine-Westphalia", "Germany", ["düsseldorf", "dusseldorf", "duesseldorf"]),
    ("Stuttgart", "Baden-Württemberg", "Germany", ["stuttgart"]),
    ("Leipzig", "Saxony", "Germany", ["leipzig"]),
    ("Amsterdam", "North Holland", "Netherlands", ["amsterdam"]),
    ("Rotterdam", "South Holland", "Netherlands", ["rotterdam"]),
    ("Utrecht", "Utrecht", "Netherlands", ["utrecht"]),
    ("The Hague", "South Holland", "Netherlands", ["the hague", "den haag"]),
    ("Eindhoven", "North Brabant", "Netherlands", ["eindhoven"]),
    ("Paris", "Île-de-France", "France", ["paris"]),
    ("Madrid", None, "Spain", ["madrid"]),
    ("Barcelona", "Catalonia", "Spain", ["barcelona"]),
    ("Lisbon", None, "Portugal", ["lisbon", "lisboa"]),
    ("Porto", None, "Portugal", ["porto"]),
    ("Milan", "Lombardy", "Italy", ["milan", "milano"]),
    ("Rome", "Lazio", "Italy", ["rome", "roma"]),
    ("Warsaw", None, "Poland", ["warsaw", "warszawa"]),
    ("Kraków", None, "Poland", ["krakow", "kraków"]),
    ("Wrocław", None, "Poland", ["wroclaw", "wrocław"]),
    ("Stockholm", None, "Sweden", ["stockholm"]),
    ("Copenhagen", None, "Denmark", ["copenhagen", "københavn"]),
    ("Oslo", None, "Norway", ["oslo"]),
    ("Helsinki", None, "Finland", ["helsinki"]),
    ("Zurich", None, "Switzerland", ["zurich", "zürich"]),
    ("Geneva", None, "Switzerland", ["geneva"]),
    ("Vienna", None, "Austria", ["vienna", "wien"]),
    ("Prague", None, "Czechia", ["prague", "praha"]),
    ("Brussels", None, "Belgium", ["brussels", "bruxelles"]),
    ("Athens", None, "Greece", ["athens"]),
    ("Thessaloniki", None, "Greece", ["thessaloniki"]),
    ("Bucharest", None, "Romania", ["bucharest"]),
    ("Sofia", None, "Bulgaria", ["sofia"]),
    ("Budapest", None, "Hungary", ["budapest"]),
    ("Istanbul", None, "Türkiye", ["istanbul", "i̇stanbul"]),
    ("Tel Aviv", None, "Israel", ["tel aviv", "tel aviv-yafo"]),
    # Rest of the world
    ("Dubai", None, "United Arab Emirates", ["dubai"]),
    ("Abu Dhabi", None, "United Arab Emirates", ["abu dhabi"]),
    ("Riyadh", None, "Saudi Arabia", ["riyadh"]),
    ("Singapore", None, "Singapore", ["singapore"]),
    ("Tokyo", None, "Japan", ["tokyo"]),
    ("Seoul", None, "South Korea", ["seoul"]),
    ("Shanghai", None, "China", ["shanghai"]),
    ("Beijing", None, "China", ["beijing"]),
    ("Hong Kong", None, "Hong Kong", ["hong kong"]),
    ("Taipei", None, "Taiwan", ["taipei"]),
    ("Sydney", "New South Wales", "Australia", ["sydney"]),
    ("Melbourne", "Victoria", "Australia", ["melbourne"]),
    ("Brisbane", "Queensland", "Australia", ["brisbane"]),
    ("Auckland", None, "New Zealand", ["auckland"]),
    ("Jakarta", None, "Indonesia", ["jakarta"]),
    ("Kuala Lumpur", None, "Malaysia", ["kuala lumpur"]),
    ("Manila", None, "Philippines", ["manila", "metro manila"]),
    ("Bangkok", None, "Thailand", ["bangkok"]),
    ("Ho Chi Minh City", None, "Vietnam", ["ho chi minh city", "ho chi minh"]),
    ("São Paulo", None, "Brazil", ["sao paulo", "são paulo"]),
    ("Mexico City", None, "Mexico", ["mexico city", "ciudad de méxico", "cdmx"]),
    ("Buenos Aires", None, "Argentina", ["buenos aires"]),
    ("Bogotá", None, "Colombia", ["bogota", "bogotá"]),
    ("Cape Town", None, "South Africa", ["cape town"]),
    ("Lagos", None, "Nigeria", ["lagos"]),
    ("Nairobi", None, "Kenya", ["nairobi"]),
]
CITY = {alias: (city, state, country) for city, state, country, aliases in _CITIES for alias in aliases}

# Words that describe an area rather than a place, or say nothing about the place
REGIONS = {"worldwide", "anywhere", "global", "globally", "emea", "europe", "eu", "apac", "asia", "latam",
           "americas", "north america", "south america", "latin america", "middle east", "africa", "asia pacific",
           "cet", "est", "pst", "utc", "gmt", "timezones", "time zones", "multiple locations", "various locations",
           "various", "multiple", "hq", "headquarters", "office", "in-office", "in office", "on-site", "onsite",
           "hybrid", "remote", "flexible", "anywhere in the world", "home based", "home-based", "work from home"}

REMOTE_WORDS = re.compile(r"\b(remote|anywhere|worldwide|work from home|wfh|home[- ]based|home ?office|distributed|flexible)\b", re.I)
PLACE_NOISE = re.compile(r"\b(office|hq|headquarters|campus)\b", re.I)
HYBRID_WORDS = re.compile(r"\bhybrid\b", re.I)
ONSITE_WORDS = re.compile(r"\b(on-?site|in[- ]office)\b", re.I)
SPLIT_SEGMENTS = re.compile(r"\s*(?:;|\||\n|\bor\b)\s*", re.I)
SPLIT_TOKENS = re.compile(r"\s*(?:,|/|\(|\)|\[|\]|\s[-–—]\s|:)\s*")


def country_of(value):
    if not value:
        return None
    v = str(value).strip()
    return COUNTRY.get(v.lower())


def _read_tokens(text):
    """Pick out city / state / country from one location phrase like 'Bengaluru, KA, India'."""
    city = state = country = None
    tokens = [t.strip(" .") for t in SPLIT_TOKENS.split(text) if t and t.strip(" .")]
    # "US-Remote", "Remote-India" or "US-San Francisco": split on a bare hyphen when one side
    # is a remote word or a country
    expanded = []
    for t in tokens:
        parts = t.split("-")
        if len(parts) == 2 and any(REMOTE_WORDS.fullmatch(p.strip()) or p.strip().lower() in COUNTRY
                                   and (p.strip().isupper() or len(p.strip()) > 3) for p in parts):
            expanded += [p.strip() for p in parts if p.strip()]
        else:
            expanded.append(t)

    for i, raw in enumerate(expanded):
        # "EMEA Remote" -> "EMEA", "Paris Office" -> "Paris"
        raw = PLACE_NOISE.sub("", HYBRID_WORDS.sub("", REMOTE_WORDS.sub("", raw))).strip(" .-")
        low = raw.lower()
        if not raw or low in REGIONS:
            continue
        # A two-letter code after a city is usually a US state: "San Francisco, CA", "Evansville, IN".
        # It is a country only when the city is known to be in that country ("Hyderabad, IN").
        if i > 0 and len(raw) == 2 and raw.isupper() and raw in US_STATES:
            known = CITY.get((city or "").lower())
            if not (known and known[2] == COUNTRY.get(low) and known[2] != "United States"):
                state = state or US_STATES[raw]
                country = country or "United States"
                continue
        if low in COUNTRY and (low not in SHORT_CODES or raw.isupper() or len(raw) == 3):
            country = country or COUNTRY[low]
            continue
        if raw.upper() in US_STATES and raw.isupper() and len(raw) == 2:
            state = state or US_STATES[raw.upper()]
            country = country or "United States"
            continue
        if raw.upper() in CA_PROVINCES and raw.isupper() and len(raw) == 2:
            state = state or CA_PROVINCES[raw.upper()]
            country = country or "Canada"
            continue
        if low in CITY and not city:
            city = CITY[low][0]
            continue
        if low in STATE:
            state = state or STATE[low][0]
            country = country or STATE[low][1]
            continue
        # Unknown place name: treat the first one as the city
        if not city and re.search(r"[^\W\d_]{3,}", raw) and len(raw) <= 40:
            city = raw.title() if raw.islower() or raw.isupper() else raw
    return city, state, country


def parse_location(location=None, city=None, region=None, country=None, remote_hint=None):
    """Return (city, state, country, workplace). Workplace is Remote, Hybrid, On-site or None."""
    text = (location or "").strip()

    # 1. Remote, hybrid or on-site: trust the source's own flag first
    hint = (remote_hint or "").lower()
    if hint == "remote":
        workplace = "Remote"
    elif hint == "hybrid":
        workplace = "Hybrid"
    elif hint == "onsite":
        workplace = "On-site"
    elif HYBRID_WORDS.search(text):
        workplace = "Hybrid"
    elif REMOTE_WORDS.search(text):
        workplace = "Remote"
    elif ONSITE_WORDS.search(text):
        workplace = "On-site"
    else:
        workplace = None

    # 2. Structured fields from the source, cleaned up
    c_city = (city or "").strip() or None
    c_state = (region or "").strip() or None
    c_country = country_of(country) or ((country or "").strip() or None)
    if c_country and c_country.upper() == c_country and len(c_country) <= 3:
        c_country = COUNTRY.get(c_country.lower(), c_country)
    if c_state and c_country == "United States" and c_state.upper() in US_STATES:
        c_state = US_STATES[c_state.upper()]
    if c_state and c_country == "India" and c_state.upper() in IN_STATE_CODES:
        c_state = IN_STATE_CODES[c_state.upper()]
    if c_state and c_country == "Canada" and c_state.upper() in CA_PROVINCES:
        c_state = CA_PROVINCES[c_state.upper()]
    if c_state and c_state.lower() in STATE:
        c_state = STATE[c_state.lower()][0]

    # 3. Otherwise read the free-text location, one segment at a time ("Pune, India; Remote")
    if not (c_city or c_country) and text:
        for segment in SPLIT_SEGMENTS.split(text):
            p_city, p_state, p_country = _read_tokens(segment)
            if p_city or p_country or p_state:
                c_city, c_state, c_country = p_city, p_state or c_state, p_country or c_country
                break

    # 4. Fill gaps from what we know about the city or state
    if c_city:
        known = CITY.get(c_city.lower())
        if known and (not c_country or known[2] == c_country):
            c_city = known[0]
            c_state = c_state or known[1]
            c_country = c_country or known[2]
    if c_state and not c_country and c_state.lower() in STATE:
        c_country = STATE[c_state.lower()][1]
    # A city that is really a state or country name ("Karnataka", "India")
    if c_city and c_city.lower() in STATE and not CITY.get(c_city.lower()):
        c_state, c_country = c_state or STATE[c_city.lower()][0], c_country or STATE[c_city.lower()][1]
        c_city = None
    if c_city and country_of(c_city):
        c_country, c_city = c_country or country_of(c_city), None
    if c_state and c_state == c_country:          # "Singapore, Singapore"
        c_state = None

    if workplace is None and c_city:
        workplace = "On-site"
    return c_city, c_state, c_country, workplace


if __name__ == "__main__":
    tests = [
        "Bengaluru, Karnataka, India", "Bangalore", "Remote - US", "US-Remote", "San Francisco, CA",
        "Seattle, San Francisco, New York City", "New York, NY (HQ)", "Remote (Canada)", "London, UK",
        "Flexible / Remote; Bengaluru, India", "Hybrid - Gurgaon", "Worldwide", "India", "Evansville, IN",
        "Hyderabad, , IN", "Delhi NCR", "Berlin", "USA", "Europe", "Karnataka, India", "EMEA Remote",
    ]
    for t in tests:
        print(f"{t!r:45} -> {parse_location(t)}")
