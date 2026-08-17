"""Synthetic benchmark corpus + query set for Week 1.

Three document categories, deliberately built to exercise the two failure
modes from concept.md:

- "semantic" docs: written with different wording than the query that should
  find them (vocabulary mismatch) -> BM25 should struggle, dense should win.
- "exact" docs: built around one rare, literal token (an error code, SKU,
  order number, exception name...) that the paired query IS -> dense should
  struggle (the token is out-of-distribution for a natural-language embedding
  model), BM25 should win easily.
- "distractor" docs: unrelated topics, present purely to dilute the corpus so
  recall@10 means something (with only 20 docs, everything is trivially in
  the top 10).

Each query lists the titles of the documents it's relevant to, resolved to
DB ids at ingestion/benchmark time (titles are unique, ids are not stable
across re-ingests).
"""

SEMANTIC_DOCS = [
    (
        "desktop-client-boot-failure",
        "The desktop client fails to initialize when the operating system "
        "finishes booting, and no window ever appears on screen.",
    ),
    (
        "large-spreadsheet-upload-freeze",
        "Users report that uploading a spreadsheet larger than 50 megabytes "
        "causes the browser tab to become unresponsive.",
    ),
    (
        "mobile-splash-screen-terminate",
        "The mobile application terminates unexpectedly a few seconds after "
        "the splash screen is shown on older Android devices.",
    ),
    (
        "duplicate-renewal-charge",
        "Subscription renewal charges are being applied twice to some "
        "customer accounts on the first day of the billing cycle.",
    ),
    (
        "printer-driver-network-drop",
        "The printer driver loses its network connection intermittently, "
        "requiring a manual restart of the print spooler service.",
    ),
    (
        "new-hire-wiki-auth-failure",
        "New employees are unable to authenticate into the internal wiki "
        "using their corporate credentials on their first day.",
    ),
    (
        "checkout-cart-empties",
        "The shopping cart empties itself if the customer navigates away "
        "from the checkout page and returns later.",
    ),
    (
        "video-call-audio-drop",
        "Video calls drop audio for a few seconds whenever a second "
        "participant joins the meeting room.",
    ),
    (
        "thermostat-firmware-reset",
        "The thermostat schedule resets to factory defaults after a "
        "firmware update is applied over the air.",
    ),
    (
        "careers-filter-not-updating",
        "Search results on the careers page do not update when a filter "
        "for remote positions is applied.",
    ),
]

SEMANTIC_QUERIES = [
    ("app won't start after reboot", "desktop-client-boot-failure"),
    ("excel file freezes the page when I try to upload it", "large-spreadsheet-upload-freeze"),
    ("app keeps crashing right after opening on my phone", "mobile-splash-screen-terminate"),
    ("got billed twice for my monthly plan", "duplicate-renewal-charge"),
    ("printer keeps disconnecting from wifi", "printer-driver-network-drop"),
    ("can't log into the company wiki with my new account", "new-hire-wiki-auth-failure"),
    ("my cart items disappeared when I came back to the site", "checkout-cart-empties"),
    ("sound cuts out when someone else joins the call", "video-call-audio-drop"),
    ("my smart thermostat lost all its settings after an update", "thermostat-firmware-reset"),
    ("filtering jobs by remote isn't changing the list", "careers-filter-not-updating"),
]

EXACT_DOCS = [
    (
        "ticket-88231-conn-timeout",
        "Ticket 88231: customer's application log shows repeated "
        "ERRCONNTIMEOUT502 entries every time the nightly batch job runs.",
    ),
    (
        "warehouse-sku-48213",
        "Warehouse audit flagged a stock discrepancy for item SKU48213BLK "
        "in aisle 12.",
    ),
    (
        "refund-order-2024088891",
        "Refund request received for order ORD2024088891, customer says "
        "the package arrived damaged.",
    ),
    (
        "deploy-log-psycopg2-error",
        "Deployment logs contain a psycopg2OperationalError right after "
        "the database connection pool is exhausted.",
    ),
    (
        "installer-hex-error-code",
        "The installer aborts and displays error code 0x8007042B on "
        "Windows 11 machines.",
    ),
    (
        "invoice-reconciliation-invus",
        "Accounts payable can't reconcile invoice INVUS99201 against the "
        "purchase order.",
    ),
    (
        "qa-regression-ticket",
        "QA flagged regression TICKETQA77410 after the last release "
        "candidate build.",
    ),
    (
        "router-firmware-model",
        "Firmware update for MODELXR2200 routers is causing the LED "
        "lights to blink amber continuously.",
    ),
    (
        "security-bulletin-cve",
        "Security bulletin references CVE202441029 affecting the legacy "
        "authentication module.",
    ),
    (
        "scheduler-stuck-batch-job",
        "The scheduler shows BATCHJOB90441 stuck in a pending state for "
        "over six hours.",
    ),
]

EXACT_QUERIES = [
    ("ERRCONNTIMEOUT502", "ticket-88231-conn-timeout"),
    ("SKU48213BLK", "warehouse-sku-48213"),
    ("ORD2024088891", "refund-order-2024088891"),
    ("psycopg2OperationalError", "deploy-log-psycopg2-error"),
    ("0x8007042B", "installer-hex-error-code"),
    ("INVUS99201", "invoice-reconciliation-invus"),
    ("TICKETQA77410", "qa-regression-ticket"),
    ("MODELXR2200", "router-firmware-model"),
    ("CVE202441029", "security-bulletin-cve"),
    ("BATCHJOB90441", "scheduler-stuck-batch-job"),
]

DISTRACTOR_DOCS = [
    ("sourdough-starter", "Sourdough bread needs a highly active starter and a long, cold overnight proof to develop its signature tangy flavor."),
    ("kyoto-tokyo-train", "The train from Kyoto to Tokyo takes just under two hours and offers views of Mount Fuji on clear days."),
    ("tomato-seedling-hardening", "Tomato seedlings should be hardened off gradually over a week before transplanting them outdoors."),
    ("marathon-route-change", "The marathon route this year was rerouted through the old harbor district due to bridge repairs."),
    ("compound-interest-timing", "Compound interest rewards starting early even more than it rewards contributing large amounts later."),
    ("library-of-alexandria", "The Library of Alexandria is believed to have housed hundreds of thousands of scrolls before its destruction."),
    ("octopus-three-hearts", "Octopuses have three hearts and can change the texture of their skin, not just its color."),
    ("unreliable-narrator-novel", "The book's unreliable narrator isn't revealed as such until the final third of the novel."),
    ("cold-front-temperature-drop", "A cold front moving in from the northwest will drop overnight temperatures by nearly fifteen degrees."),
    ("cat-kneading-instinct", "Cats knead with their paws as a leftover instinct from kneading their mother during nursing."),
    ("vineyard-harvest-delay", "The vineyard's harvest was delayed two weeks this year because of an unusually cool, wet spring."),
    ("chess-opening-memorization", "Chess grandmasters often memorize entire opening lines dozens of moves deep before a tournament."),
    ("hiking-trail-elevation", "The hiking trail gains most of its elevation in the final mile, switchbacking up an exposed ridge."),
    ("basalt-column-formation", "Basalt columns form when thick lava flows cool slowly and crack into hexagonal patterns."),
    ("concert-hall-acoustics", "The orchestra's new concert hall was designed with movable panels to adjust its acoustics per performance."),
    ("beekeeping-first-harvest", "Beekeepers typically wait until the second year before harvesting honey from a new hive."),
    ("tram-network-rebuild", "The city's tram network was rebuilt from scratch after being dismantled decades earlier for buses."),
    ("sea-turtle-nesting", "Sea turtles return to the same beach where they hatched, sometimes decades later, to lay their own eggs."),
    ("cast-iron-seasoning", "A well-seasoned cast iron skillet develops a natural non-stick coating from repeated use with oil."),
    ("museum-textile-wing", "The museum's new wing is dedicated entirely to textiles and weaving traditions from the region."),
    ("negative-split-cycling", "Long-distance cyclists often practice negative-split pacing, riding the second half faster than the first."),
    ("volcanic-soil-fertility", "Volcanic soil near the mountain's base is unusually fertile, which is why so many farms cluster there."),
    ("novel-serialized-magazine", "The novel was originally serialized in a magazine before being published as a single volume."),
    ("espresso-grind-sensitivity", "Espresso extraction time is highly sensitive to grind size, sometimes by just a few microns."),
    ("observatory-new-moon-schedule", "The observatory schedules its clearest viewing nights around the new moon to minimize light interference."),
    ("rowing-stroke-rate-sound", "Competitive rowers coordinate their stroke rate almost entirely by sound rather than looking at each other."),
    ("lighthouse-cottage-museum", "The old lighthouse keeper's cottage was converted into a small maritime museum a decade ago."),
    ("fermented-food-cultures", "Fermented foods rely on specific bacterial cultures that vary widely by region and tradition."),
    ("pedestrian-bridge-funding", "The city council approved funding for a new pedestrian bridge connecting the two riverside parks."),
    ("migratory-bird-altitude", "Migratory birds adjust their flight altitude based on wind patterns at different times of day."),
]

# "Near-miss" distractors: same general topic as one EXACT_DOCS entry (timeout,
# SKU/warehouse, refund order, deployment DB error, installer error code, invoice,
# QA regression, router firmware, security bulletin, batch job) but built around a
# *different* incident and with no literal token overlap with the paired exact
# query. These are what actually stress dense retrieval at k=10: a generic
# embedding model has little to hold onto in an EXACT_DOCS entry besides "this is
# an IT/ops ticket", so once several same-topic near-misses exist, the one true
# match can get crowded out of the top 10 purely on semantic similarity -- while
# BM25 still separates them instantly because only one document contains the
# literal token the query IS.
NEAR_MISS_DOCS = [
    ("ticket-91442-api-timeout", "Ticket 91442: customer reports repeated timeout errors connecting to the API gateway during peak traffic hours."),
    ("warehouse-audit-aisle-7", "Warehouse audit found a quantity mismatch for a different SKU in aisle 7 last week."),
    ("refund-cracked-case-order", "A separate refund request was filed for an order that arrived with a cracked case."),
    ("deploy-log-pool-warning", "Deployment logs show a database connection pool exhaustion warning before the last outage."),
    ("installer-different-error", "The installer displayed a different Windows error code during a clean install on a test machine."),
    ("invoice-different-vendor", "Accounts payable is still waiting on a corrected invoice from a different vendor this quarter."),
    ("qa-new-regression-ticket", "QA opened a new regression ticket after the previous release candidate's build failed."),
    ("router-different-model-led", "A firmware rollout to a different router model caused the status light to flash red instead of amber."),
    ("security-unrelated-library", "The security team published a bulletin about a vulnerability in an unrelated authentication library."),
    ("batch-job-different-queue", "A different batch job has been stuck in a queued state since early this morning."),
    ("support-eu-cluster-timeout", "Support escalated a networking timeout that only affects customers on the EU cluster."),
    ("fulfillment-barcode-mismatch", "The fulfillment center flagged a barcode that doesn't match any item in the current catalog."),
    ("billing-disputed-order", "Billing opened an investigation into a customer's disputed order from last month."),
    ("staging-connection-error", "The staging environment threw a connection error right after a dependency upgrade."),
    ("laptop-boot-failure-update", "IT logged a new ticket after a laptop failed to boot following a routine update."),
    ("procurement-overdue-invoice", "Procurement is chasing down an overdue invoice from last quarter's hardware order."),
    ("regression-reopened-early", "The release manager reopened a regression that QA had marked resolved too early."),
    ("router-overheating-closet", "Field engineers reported the same router model overheating in a hot server closet."),
    ("compliance-expired-cert", "The compliance team is reviewing a bulletin about an expired security certificate."),
    ("batch-pipeline-silent-fail", "Operations restarted a batch pipeline that had been silently failing for two days."),
]

# "Combined" docs: each pairs a paraphrasable complaint (the semantic failure
# mode) with one literal token (the exact failure mode) in the *same*
# document, and the paired query reuses both -- a differently-worded
# paraphrase of the complaint plus the token verbatim. Each has a near-miss
# twin describing an almost-identical complaint but a *different* token, so
# topic similarity alone isn't enough to pick the right one; only a
# retriever (or fusion) that also honors the token gets it right every time.
COMBINED_DOCS = [
    (
        "combined-invoice-duplicate-charge",
        "Ticket TCKTBILL5521: a customer was billed twice for the same "
        "invoice after retrying a failed payment, and support needs to "
        "issue a manual refund.",
    ),
    (
        "combined-vpn-drop-oncall",
        "Incident INCVPN6634: the VPN connection drops every time an "
        "on-call engineer's laptop goes to sleep, forcing a full "
        "reconnect and re-authentication.",
    ),
    (
        "combined-export-button-disabled",
        "Case CASEXPT4471: the export button on the analytics dashboard "
        "stays greyed out for users on the free trial plan, even after "
        "upgrading to a paid seat.",
    ),
    (
        "combined-notification-delay-mobile",
        "Bug BUGNOTIF8802: push notifications on the mobile app arrive up "
        "to twenty minutes late for users on the latest OS beta build.",
    ),
    (
        "combined-api-key-rotation-fail",
        "Ticket TCKTAPIKEY9013: rotating an API key in the admin console "
        "silently fails and the old key keeps working instead of being "
        "revoked.",
    ),
]

COMBINED_NEAR_MISS_DOCS = [
    (
        "combined-invoice-duplicate-charge-nearmiss",
        "A different customer also reports being billed twice after a "
        "retried payment, but that case was already resolved by the "
        "billing team last week.",
    ),
    (
        "combined-vpn-drop-oncall-nearmiss",
        "Another engineer reported a similar VPN disconnect issue on wake "
        "from sleep, but it turned out to be caused by an outdated network "
        "driver, not the VPN client.",
    ),
    (
        "combined-export-button-disabled-nearmiss",
        "A similar case describes the export button being disabled on the "
        "dashboard, but for a completely unrelated reason tied to browser "
        "extensions blocking the click.",
    ),
    (
        "combined-notification-delay-mobile-nearmiss",
        "There's a related report of delayed mobile push notifications, "
        "but investigation showed it only affects users on a specific "
        "regional carrier network.",
    ),
    (
        "combined-api-key-rotation-fail-nearmiss",
        "A separate ticket also mentions API key rotation problems in the "
        "admin console, but that one was actually a documentation issue, "
        "not a functional bug.",
    ),
]

COMBINED_QUERIES = [
    (
        "customer got charged twice when their payment retried, reference TCKTBILL5521",
        "combined-invoice-duplicate-charge",
    ),
    (
        "vpn keeps dropping whenever my laptop wakes up from sleep, incident INCVPN6634",
        "combined-vpn-drop-oncall",
    ),
    (
        "export option is stuck greyed out on the dashboard after upgrading my plan, case CASEXPT4471",
        "combined-export-button-disabled",
    ),
    (
        "notifications on my phone show up way late since the newest beta update, bug BUGNOTIF8802",
        "combined-notification-delay-mobile",
    ),
    (
        "when I rotate my API key in the admin panel it doesn't actually revoke the old one, ticket TCKTAPIKEY9013",
        "combined-api-key-rotation-fail",
    ),
]

DOCUMENTS = (
    SEMANTIC_DOCS
    + EXACT_DOCS
    + DISTRACTOR_DOCS
    + NEAR_MISS_DOCS
    + COMBINED_DOCS
    + COMBINED_NEAR_MISS_DOCS
)
QUERIES = (
    [
        {"query": q, "relevant_titles": [title], "category": "semantic"}
        for q, title in SEMANTIC_QUERIES
    ]
    + [
        {"query": q, "relevant_titles": [title], "category": "exact"}
        for q, title in EXACT_QUERIES
    ]
    + [
        {"query": q, "relevant_titles": [title], "category": "combined"}
        for q, title in COMBINED_QUERIES
    ]
)
