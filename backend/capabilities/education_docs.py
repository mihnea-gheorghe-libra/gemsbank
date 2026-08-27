import re
from dataclasses import dataclass
from functools import lru_cache

_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass(slots=True, frozen=True)
class EducationDoc:
    id: str
    label_en: str
    label_ro: str
    body_en: str
    body_ro: str


_DOCS: list[EducationDoc] = [
    EducationDoc(
        id="emergency-fund",
        label_en="What's an emergency fund?",
        label_ro="Ce este un fond de urgență?",
        body_en=(
            "An emergency fund is money kept in an easy-access account, not invested, so a lost "
            "job, a medical bill or a broken appliance doesn't force you into debt. A common "
            "starting target is 3-6 months of essential expenses, built gradually with a fixed "
            "amount each month, before chasing higher-return goals."
        ),
        body_ro=(
            "Un fond de urgență este o sumă păstrată într-un cont cu acces rapid, neinvestită, "
            "astfel încât pierderea unui loc de muncă, o factură medicală sau un aparat stricat "
            "să nu te oblige să te împrumuți. O țintă obișnuită de pornire este 3-6 luni de "
            "cheltuieli esențiale, construită treptat, cu o sumă fixă în fiecare lună, înainte de "
            "a urmări obiective cu randament mai mare."
        ),
    ),
    EducationDoc(
        id="budgeting-503020",
        label_en="A simple budgeting split (50/30/20)",
        label_ro="O împărțire simplă a bugetului (50/30/20)",
        body_en=(
            "One widely used rule of thumb splits take-home income into three buckets: about 50% "
            "for needs (housing, utilities, groceries), 30% for wants (dining out, hobbies), and "
            "20% for savings and debt repayment. It's a starting template, not a law — adjust the "
            "split to your own fixed costs and goals."
        ),
        body_ro=(
            "O regulă generală des folosită împarte venitul net în trei categorii: aproximativ "
            "50% pentru nevoi (locuință, utilități, alimente), 30% pentru dorințe (ieșiri, "
            "hobby-uri) și 20% pentru economii și rambursarea datoriilor. Este un șablon de "
            "pornire, nu o regulă fixă — ajustează procentele la costurile și obiectivele tale."
        ),
    ),
    EducationDoc(
        id="compound-interest",
        label_en="How compound interest works",
        label_ro="Cum funcționează dobânda compusă",
        body_en=(
            "Simple interest is paid only on your original deposit. Compound interest is paid on "
            "your deposit plus everything it has already earned, so the balance grows faster the "
            "longer it's left alone. Two savers depositing the same amount can reach very "
            "different totals if one starts a few years earlier — time in the account matters as "
            "much as the rate."
        ),
        body_ro=(
            "Dobânda simplă se plătește doar la suma depusă inițial. Dobânda compusă se plătește "
            "la depozit plus tot ce a acumulat deja, deci soldul crește mai repede cu cât banii "
            "stau mai mult neatinși. Doi economisitori care depun aceeași sumă pot ajunge la "
            "totaluri foarte diferite dacă unul începe cu câțiva ani mai devreme — timpul contează "
            "aproape la fel de mult ca rata dobânzii."
        ),
    ),
    EducationDoc(
        id="inflation",
        label_en="Inflation and your savings",
        label_ro="Inflația și economiile tale",
        body_en=(
            "Inflation is the general rise in prices over time. Cash sitting at 0% loses "
            "purchasing power every year inflation is positive — the same balance buys less next "
            "year than it does today. Keeping some savings in interest-bearing accounts, rather "
            "than only as idle cash, helps preserve what that money can actually buy."
        ),
        body_ro=(
            "Inflația este creșterea generală a prețurilor în timp. Banii ținuți la 0% dobândă "
            "pierd din puterea de cumpărare în fiecare an în care inflația este pozitivă — același "
            "sold cumpără mai puțin anul viitor decât astăzi. Păstrarea unei părți din economii în "
            "conturi purtătoare de dobândă, nu doar ca bani inactivi, ajută la păstrarea puterii "
            "reale de cumpărare."
        ),
    ),
    EducationDoc(
        id="savings-vs-term-deposit",
        label_en="Savings account vs. term deposit",
        label_ro="Cont de economii vs. depozit la termen",
        body_en=(
            "A savings account lets you withdraw whenever you need to, typically at a lower rate. "
            "A term deposit locks the money away for a fixed period in exchange for a usually "
            "higher rate, with an early-withdrawal penalty if you break it. Match the product to "
            "how soon you might realistically need the money."
        ),
        body_ro=(
            "Un cont de economii permite retragerea oricând, de obicei la o dobândă mai mică. Un "
            "depozit la termen blochează banii pentru o perioadă fixă în schimbul unei dobânzi de "
            "obicei mai mari, cu o penalizare dacă retragi mai devreme. Alege produsul în funcție "
            "de cât de curând ai putea avea nevoie realmente de bani."
        ),
    ),
    EducationDoc(
        id="fixed-vs-variable-rate",
        label_en="Fixed vs. variable interest rates",
        label_ro="Dobândă fixă vs. dobândă variabilă",
        body_en=(
            "A fixed rate stays the same for the whole term, so you know exactly what you'll earn "
            "or pay. A variable rate can rise or fall with the wider market, which can work in "
            "your favour or against it. Fixed rates suit predictability; variable rates suit "
            "flexibility and can pay off when rates are falling."
        ),
        body_ro=(
            "O dobândă fixă rămâne aceeași pe toată durata contractului, deci știi exact cât vei "
            "câștiga sau plăti. O dobândă variabilă poate crește sau scădea odată cu piața, ceea "
            "ce poate fi în favoarea ta sau împotriva ei. Dobânda fixă e potrivită pentru "
            "predictibilitate; cea variabilă pentru flexibilitate."
        ),
    ),
    EducationDoc(
        id="debt-payoff-order",
        label_en="Which debt to pay off first",
        label_ro="Ce datorie să achiți mai întâi",
        body_en=(
            "Two common approaches: the avalanche method pays off the debt with the highest "
            "interest rate first, which minimises total interest paid over time. The snowball "
            "method pays off the smallest balance first, which builds momentum and motivation "
            "even though it may cost slightly more in interest. Either beats paying only the "
            "minimum everywhere and letting high-rate debt compound."
        ),
        body_ro=(
            "Două abordări obișnuite: metoda avalanșă achită mai întâi datoria cu cea mai mare "
            "dobândă, ceea ce minimizează dobânda totală plătită în timp. Metoda bulgăre de "
            "zăpadă achită mai întâi soldul cel mai mic, ceea ce construiește motivație, chiar "
            "dacă poate costa puțin mai mult în dobândă. Oricare dintre ele e mai bună decât a "
            "plăti doar minimul peste tot și a lăsa datoria cu dobândă mare să se acumuleze."
        ),
    ),
    EducationDoc(
        id="diversification",
        label_en="Why diversification matters",
        label_ro="De ce contează diversificarea",
        body_en=(
            "Diversification means spreading money across different assets so that one bad "
            "outcome doesn't sink the whole plan. It doesn't guarantee a profit or eliminate "
            "risk, but it reduces how much a single company, sector or market can hurt you. This "
            "is a general principle, not investment advice for any specific product."
        ),
        body_ro=(
            "Diversificarea înseamnă distribuirea banilor pe active diferite, astfel încât un "
            "singur eveniment negativ să nu afecteze tot planul. Nu garantează un profit și nu "
            "elimină riscul, dar reduce cât de mult te poate afecta o singură companie, un singur "
            "sector sau o singură piață. Acesta este un principiu general, nu o recomandare de "
            "investiție pentru un produs anume."
        ),
    ),
    EducationDoc(
        id="deposit-guarantee",
        label_en="What the deposit guarantee scheme covers",
        label_ro="Ce acoperă schema de garantare a depozitelor",
        body_en=(
            "In the EU, bank deposits are protected by a deposit guarantee scheme up to a "
            "harmonised ceiling per depositor per bank (currently €100,000, or the RON "
            "equivalent). It covers savings and current accounts if the bank itself fails — it "
            "does not cover losses from investments, market movements, or fraud on your own part."
        ),
        body_ro=(
            "În UE, depozitele bancare sunt protejate printr-o schemă de garantare a depozitelor, "
            "până la un plafon armonizat pe deponent și pe bancă (în prezent 100.000 EUR, sau "
            "echivalentul în RON). Aceasta acoperă conturile de economii și curente în cazul în "
            "care banca dă faliment — nu acoperă pierderile din investiții, din mișcări de piață, "
            "sau din fraudă."
        ),
    ),
    EducationDoc(
        id="apr-explained",
        label_en="What APR / annual rate actually means",
        label_ro="Ce înseamnă de fapt DAE / rata anuală",
        body_en=(
            "The annual percentage rate expresses the cost (for a loan) or the return (for "
            "savings) as if it applied over a full year, so products with different terms or "
            "compounding schedules can be compared on the same basis. Always compare the annual "
            "rate, not the headline monthly figure, when comparing two offers."
        ),
        body_ro=(
            "Dobânda anuală exprimă costul (pentru un credit) sau randamentul (pentru economii) "
            "ca și cum s-ar aplica pe un an întreg, astfel încât produse cu termene sau frecvențe "
            "de capitalizare diferite pot fi comparate pe aceeași bază. Compară întotdeauna rata "
            "anuală, nu cifra lunară afișată, când compari două oferte."
        ),
    ),
    EducationDoc(
        id="smart-goals",
        label_en="What makes a savings goal SMART",
        label_ro="Ce face un obiectiv de economisire SMART",
        body_en=(
            "A SMART goal is Specific (a named purpose, not just 'save more'), Measurable (a "
            "concrete target amount), Achievable (realistic against your actual income and "
            "expenses), Relevant (something that matters to you), and Time-bound (a target date). "
            "Turning a vague wish into these five parts is what makes a goal something you can "
            "actually track progress against."
        ),
        body_ro=(
            "Un obiectiv SMART este Specific (un scop numit, nu doar 'să economisesc mai mult'), "
            "Măsurabil (o sumă țintă concretă), Accesibil (realist față de venitul și cheltuielile "
            "tale reale), Relevant (ceva important pentru tine) și încadrat în Timp (o dată "
            "țintă). Transformarea unei dorințe vagi în aceste cinci elemente este ce face un "
            "obiectiv urmăribil."
        ),
    ),
]


def _clean(text: str) -> str:
    return text.strip()


@lru_cache(maxsize=1)
def load_education_docs() -> list[EducationDoc]:
    return list(_DOCS)


def _score(doc: EducationDoc, terms: set[str]) -> int:
    haystack = f"{doc.label_en} {doc.label_ro} {doc.body_en} {doc.body_ro}".lower()
    words = set(_WORD.findall(haystack))
    return len(terms & words)


def search_education_docs(query: str, limit: int = 4) -> list[EducationDoc]:
    docs = load_education_docs()
    terms = {word for word in _WORD.findall(query.lower()) if len(word) > 2}
    ranked = sorted(docs, key=lambda doc: _score(doc, terms), reverse=True)
    matched = [doc for doc in ranked if _score(doc, terms) > 0]
    return (matched or docs)[:limit]
