from dataclasses import dataclass
from functools import lru_cache


@dataclass(slots=True, frozen=True)
class QuizOption:
    id: str
    label_en: str
    label_ro: str


@dataclass(slots=True, frozen=True)
class QuizQuestion:
    id: str
    prompt_en: str
    prompt_ro: str
    options: tuple[QuizOption, ...]
    correct_option_id: str
    explanation_en: str
    explanation_ro: str


@dataclass(slots=True, frozen=True)
class Lesson:
    id: str
    title_en: str
    title_ro: str
    body_en: str
    body_ro: str
    questions: tuple[QuizQuestion, ...]


def _q(
    qid: str,
    prompt_en: str,
    prompt_ro: str,
    options: list[tuple[str, str, str]],
    correct: str,
    explanation_en: str,
    explanation_ro: str,
) -> QuizQuestion:
    return QuizQuestion(
        id=qid,
        prompt_en=prompt_en,
        prompt_ro=prompt_ro,
        options=tuple(QuizOption(oid, en, ro) for oid, en, ro in options),
        correct_option_id=correct,
        explanation_en=explanation_en,
        explanation_ro=explanation_ro,
    )


_LESSONS: list[Lesson] = [
    Lesson(
        id="budgeting",
        title_en="Budgeting in three buckets",
        title_ro="Bugetul în trei categorii",
        body_en=(
            "A budget is simply a plan for money you have not spent yet. A common starting "
            "template splits your take-home pay into roughly 50% for needs such as rent, "
            "utilities and groceries, 30% for wants, and 20% for savings and debt repayment. "
            "The exact percentages matter far less than writing them down and checking, once a "
            "month, whether reality matched the plan. "
            "The first month is mostly measurement rather than discipline: you write down what you "
            "actually spent and find out which bucket is genuinely the tight one. From then on the "
            "useful question is not whether you overspent, but which single line you will change "
            "next month — one subscription dropped, or one category given a firm weekly limit — "
            "because a budget you adjust survives, while one you rewrite from scratch every time "
            "quietly gets abandoned."
        ),
        body_ro=(
            "Un buget este pur și simplu un plan pentru banii pe care încă nu i-ai cheltuit. Un "
            "șablon obișnuit de pornire împarte venitul net în aproximativ 50% pentru nevoi "
            "(chirie, utilități, alimente), 30% pentru dorințe și 20% pentru economii și "
            "rambursarea datoriilor. Procentele exacte contează mult mai puțin decât faptul că "
            "le scrii undeva și verifici, o dată pe lună, dacă realitatea a semănat cu planul. "
            "Prima lună este mai degrabă o măsurătoare decât un exercițiu de disciplină: notezi ce "
            "ai cheltuit de fapt și afli care categorie este cu adevărat strâmtă. De atunci "
            "înainte, întrebarea utilă nu este dacă ai depășit bugetul, ci ce singură linie schimbi "
            "luna următoare — un abonament la care renunți sau o categorie căreia îi pui o limită "
            "săptămânală fermă — pentru că un buget pe care îl ajustezi supraviețuiește, iar unul "
            "pe care îl rescrii de la zero de fiecare dată este abandonat discret."
        ),
        questions=(
            _q(
                "budgeting-1",
                "In the 50/30/20 split, what does the 50% cover?",
                "În împărțirea 50/30/20, ce acoperă cei 50%?",
                [
                    ("a", "Needs: rent, utilities, groceries", "Nevoi: chirie, utilități, alimente"),
                    ("b", "Wants: dining out, hobbies", "Dorințe: ieșiri, hobby-uri"),
                    ("c", "Savings and debt repayment", "Economii și rambursarea datoriilor"),
                ],
                "a",
                "The largest bucket covers essentials you cannot easily avoid.",
                "Categoria cea mai mare acoperă cheltuielile esențiale, greu de evitat.",
            ),
            _q(
                "budgeting-2",
                "Where does debt repayment sit in the 50/30/20 template?",
                "Unde se încadrează rambursarea datoriilor în șablonul 50/30/20?",
                [
                    ("a", "In the 50% for needs", "În cei 50% pentru nevoi"),
                    ("b", "In the 20%, together with savings", "În cei 20%, împreună cu economiile"),
                    ("c", "It is not part of the template", "Nu face parte din șablon"),
                ],
                "b",
                "Savings and debt repayment share the same 20% bucket.",
                "Economiile și rambursarea datoriilor împart aceeași categorie de 20%.",
            ),
            _q(
                "budgeting-3",
                "A budget is best described as:",
                "Un buget este descris cel mai bine ca:",
                [
                    ("a", "A record of what you already spent", "O evidență a ceea ce ai cheltuit deja"),
                    ("b", "A plan for money you have not spent yet", "Un plan pentru banii pe care încă nu i-ai cheltuit"),
                    ("c", "A limit your bank enforces", "O limită impusă de bancă"),
                ],
                "b",
                "It looks forward. Tracking past spending is useful, but that is not the budget itself.",
                "Se uită înainte. Urmărirea cheltuielilor trecute e utilă, dar nu este bugetul în sine.",
            ),
            _q(
                "budgeting-4",
                "Your rent alone takes 60% of your take-home pay. What should you do?",
                "Doar chiria îți ia 60% din venitul net. Ce ar trebui să faci?",
                [
                    ("a", "Adjust the split to your real fixed costs", "Ajustezi procentele la costurile tale fixe reale"),
                    ("b", "Stop budgeting, the template does not apply", "Renunți la buget, șablonul nu se aplică"),
                    ("c", "Borrow to bring rent back under 50%", "Te împrumuți ca să aduci chiria sub 50%"),
                ],
                "a",
                "50/30/20 is a starting template, not a rule. Adapt it to your own fixed costs.",
                "50/30/20 este un șablon de pornire, nu o regulă. Adaptează-l la costurile tale fixe.",
            ),
            _q(
                "budgeting-5",
                "How often should you compare the plan against reality?",
                "Cât de des ar trebui să compari planul cu realitatea?",
                [
                    ("a", "Every day", "În fiecare zi"),
                    ("b", "About once a month", "Aproximativ o dată pe lună"),
                    ("c", "Only when money runs out", "Doar când rămâi fără bani"),
                ],
                "b",
                "A monthly check is frequent enough to catch drift without becoming a chore.",
                "O verificare lunară e destul de deasă cât să prinzi abaterile, fără să devină o corvoadă.",
            ),
        ),
    ),
    Lesson(
        id="emergency-fund",
        title_en="The emergency fund",
        title_ro="Fondul de urgență",
        body_en=(
            "An emergency fund is money kept in an easy-access account, not invested, so that a "
            "lost job, a medical bill or a broken boiler does not force you into debt. A common "
            "target is three to six months of essential expenses. Build it before you chase "
            "higher returns: its job is not to grow, it is to be there on the worst day. "
            "Three to six months is a range, not a rule: a steady salary and a second income in the "
            "household sit at the lower end, while freelance or seasonal work belongs at the higher "
            "one. Keep it in a separate account so it is not spent by accident, and treat using it "
            "as the fund doing its job rather than as a failure — you simply refill it once the "
            "emergency has passed."
        ),
        body_ro=(
            "Un fond de urgență este o sumă păstrată într-un cont cu acces rapid, neinvestită, "
            "astfel încât pierderea locului de muncă, o factură medicală sau o centrală stricată "
            "să nu te oblige să te împrumuți. O țintă obișnuită este de trei până la șase luni de "
            "cheltuieli esențiale. Construiește-l înainte să urmărești randamente mari: rolul lui "
            "nu este să crească, ci să fie acolo în cea mai proastă zi. "
            "Trei până la șase luni este un interval, nu o regulă: un salariu stabil și un al "
            "doilea venit în gospodărie te așază la capătul de jos, în timp ce munca pe cont "
            "propriu sau sezonieră cere capătul de sus. Ține-l într-un cont separat, ca să nu îl "
            "cheltuiești din greșeală, și privește folosirea lui ca pe fondul care își face treaba, "
            "nu ca pe un eșec — pur și simplu îl reîntregești după ce trece urgența."
        ),
        questions=(
            _q(
                "emergency-fund-1",
                "An emergency fund is usually sized as:",
                "Un fond de urgență se dimensionează de obicei ca:",
                [
                    ("a", "Three to six months of essential expenses", "Trei până la șase luni de cheltuieli esențiale"),
                    ("b", "Ten percent of your annual salary", "Zece la sută din salariul anual"),
                    ("c", "Whatever is left at the end of the year", "Cât rămâne la sfârșitul anului"),
                ],
                "a",
                "It is measured in months of expenses so it keeps pace with what your life costs.",
                "Se măsoară în luni de cheltuieli, ca să țină pasul cu cât costă viața ta.",
            ),
            _q(
                "emergency-fund-2",
                "Where should an emergency fund be kept?",
                "Unde ar trebui ținut un fond de urgență?",
                [
                    ("a", "Invested in shares for growth", "Investit în acțiuni, pentru creștere"),
                    ("b", "In an easy-access account, not invested", "Într-un cont cu acces rapid, neinvestit"),
                    ("c", "Locked away until a fixed date", "Blocat până la o dată fixă"),
                ],
                "b",
                "You need it available on the day something goes wrong, at a predictable value.",
                "Ai nevoie de el disponibil în ziua în care ceva merge prost, la o valoare previzibilă.",
            ),
            _q(
                "emergency-fund-3",
                "What is the main purpose of an emergency fund?",
                "Care este scopul principal al unui fond de urgență?",
                [
                    ("a", "To earn a better return than a current account", "Să obții un randament mai bun decât la contul curent"),
                    ("b", "To avoid being forced into debt when something goes wrong", "Să nu fii nevoit să te împrumuți când ceva merge prost"),
                    ("c", "To improve your credit score", "Să îți îmbunătățești scorul de credit"),
                ],
                "b",
                "Its job is not to grow. It is to be there on the worst day.",
                "Rolul lui nu este să crească, ci să fie acolo în cea mai proastă zi.",
            ),
            _q(
                "emergency-fund-4",
                "Should you build an emergency fund before or after chasing higher returns?",
                "Construiești fondul de urgență înainte sau după ce urmărești randamente mai mari?",
                [
                    ("a", "Before", "Înainte"),
                    ("b", "After", "După"),
                    ("c", "It makes no difference", "Nu contează"),
                ],
                "a",
                "Without it, one bad month can force you to sell investments at the worst moment.",
                "Fără el, o lună proastă te poate obliga să vinzi investiții în cel mai prost moment.",
            ),
            _q(
                "emergency-fund-5",
                "Why is the target set in months of expenses rather than a fixed sum?",
                "De ce ținta se stabilește în luni de cheltuieli și nu ca sumă fixă?",
                [
                    ("a", "Because banks require it that way", "Pentru că băncile cer așa"),
                    ("b", "So it keeps pace with what your life actually costs", "Ca să țină pasul cu cât costă de fapt viața ta"),
                    ("c", "Because a fixed sum is harder to calculate", "Pentru că o sumă fixă e mai greu de calculat"),
                ],
                "b",
                "A sum decided years ago quietly becomes too small as prices rise.",
                "O sumă stabilită acum câțiva ani devine discret prea mică pe măsură ce prețurile cresc.",
            ),
        ),
    ),
    Lesson(
        id="simple-vs-compound-interest",
        title_en="Simple interest vs compound interest",
        title_ro="Dobânda simplă vs dobânda compusă",
        body_en=(
            "Simple interest is paid only on the amount you originally put in. Compound interest "
            "is paid on your deposit plus every bit of interest it has already earned, so the "
            "balance accelerates the longer it is left alone. Over one year the two are almost "
            "identical; over twenty years the gap is dramatic. The same mechanism works against "
            "you on unpaid credit-card debt. "
            "Two things decide how much compounding does for you: how early you start and how "
            "rarely you interrupt it, and both matter more than hunting for a slightly better rate. "
            "A rough check is to divide 72 by the annual rate to see how many years the balance "
            "takes to double — at 6% that is about twelve years, and every withdrawal restarts part "
            "of that clock."
        ),
        body_ro=(
            "Dobânda simplă se plătește doar la suma pe care ai depus-o inițial. Dobânda compusă "
            "se plătește la depozit plus la toată dobânda deja acumulată, așa că soldul "
            "accelerează cu cât este lăsat mai mult în pace. Pe un an, cele două sunt aproape "
            "identice; pe douăzeci de ani, diferența este uriașă. Același mecanism lucrează "
            "împotriva ta la datoria neplătită de pe cardul de credit. "
            "Două lucruri decid cât face dobânda compusă pentru tine: cât de devreme începi și cât "
            "de rar întrerupi, iar ambele cântăresc mai mult decât vânătoarea unei dobânzi cu puțin "
            "mai bune. O verificare rapidă este să împarți 72 la dobânda anuală ca să vezi în câți "
            "ani se dublează soldul — la 6% înseamnă aproximativ doisprezece ani, iar fiecare "
            "retragere pornește din nou o parte din acest ceas."
        ),
        questions=(
            _q(
                "compound-1",
                "Simple interest is paid on:",
                "Dobânda simplă se plătește la:",
                [
                    ("a", "Only the amount you originally deposited", "Doar suma depusă inițial"),
                    ("b", "The deposit plus interest already earned", "Depozit plus dobânda deja acumulată"),
                    ("c", "Only the interest, never the deposit", "Doar dobânda, niciodată la depozit"),
                ],
                "a",
                "Simple interest ignores what the balance has already earned.",
                "Dobânda simplă ignoră ce a acumulat deja soldul.",
            ),
            _q(
                "compound-2",
                "What makes compound interest different?",
                "Ce diferențiază dobânda compusă?",
                [
                    ("a", "It is always a higher advertised rate", "Are întotdeauna o rată afișată mai mare"),
                    ("b", "It also pays interest on the interest already earned", "Plătește dobândă și la dobânda deja acumulată"),
                    ("c", "It is paid only when you close the account", "Se plătește doar când închizi contul"),
                ],
                "b",
                "Interest earning its own interest is what makes the balance accelerate.",
                "Dobânda care produce la rândul ei dobândă face soldul să accelereze.",
            ),
            _q(
                "compound-3",
                "Over what horizon does the gap between the two become dramatic?",
                "Pe ce orizont devine uriașă diferența dintre cele două?",
                [
                    ("a", "A few months", "Câteva luni"),
                    ("b", "About one year", "Aproximativ un an"),
                    ("c", "Many years or decades", "Mulți ani sau decenii"),
                ],
                "c",
                "Over one year the two are almost identical; time is what creates the difference.",
                "Pe un an sunt aproape identice; timpul este cel care creează diferența.",
            ),
            _q(
                "compound-4",
                "Compounding works against you on:",
                "Compunerea lucrează împotriva ta la:",
                [
                    ("a", "Unpaid credit-card debt", "Datoria neplătită de pe cardul de credit"),
                    ("b", "A savings account", "Un cont de economii"),
                    ("c", "An emergency fund", "Un fond de urgență"),
                ],
                "a",
                "The same mechanism that grows savings also grows what you owe.",
                "Același mecanism care crește economiile crește și cât datorezi.",
            ),
            _q(
                "compound-5",
                "Two people deposit the same amount at the same rate. Who ends up with more?",
                "Două persoane depun aceeași sumă, la aceeași rată. Cine ajunge cu mai mult?",
                [
                    ("a", "The one who leaves it untouched for longer", "Cea care îi lasă neatinși mai mult timp"),
                    ("b", "The one who checks the balance more often", "Cea care verifică soldul mai des"),
                    ("c", "They always end up equal", "Ajung mereu la egalitate"),
                ],
                "a",
                "With compounding, time in the account is what does the work.",
                "La dobânda compusă, timpul petrecut în cont este cel care lucrează.",
            ),
        ),
    ),
    Lesson(
        id="credit-score",
        title_en="What a credit score measures",
        title_ro="Ce măsoară scorul de credit",
        body_en=(
            "A credit score is a summary of how reliably you have repaid borrowed money. Paying "
            "on time is the single largest factor; how much of your available credit you "
            "routinely use comes next, and a longer history helps. It is not a measure of wealth "
            "or income — someone with a high salary and missed payments can score worse than "
            "someone modest who always pays on the due date. "
            "Two habits move it more than anything else: paying every instalment on the due date, "
            "and keeping the balance you carry well below the limit you were given instead of "
            "living at the edge of it. Applying for several loans or cards in quick succession also "
            "leaves a mark, so it is worth spacing applications out when you know a mortgage or a "
            "car loan is coming."
        ),
        body_ro=(
            "Scorul de credit este rezumatul modului în care ai rambursat banii împrumutați. "
            "Plata la timp este factorul cel mai important; urmează cât din creditul disponibil "
            "folosești în mod obișnuit, iar un istoric mai lung ajută. Nu este o măsură a averii "
            "sau a venitului — cineva cu salariu mare și plăți întârziate poate avea un scor mai "
            "slab decât cineva modest care plătește mereu la scadență. "
            "Două obiceiuri îl mișcă mai mult decât orice altceva: plata fiecărei rate la scadență "
            "și menținerea soldului folosit mult sub limita primită, în loc să trăiești la marginea "
            "ei. Și cererile de mai multe credite sau carduri într-un interval scurt lasă urme, așa "
            "că merită să le distanțezi atunci când știi că urmează un credit ipotecar sau unul "
            "auto."
        ),
        questions=(
            _q(
                "credit-score-1",
                "Which has the biggest effect on a credit score?",
                "Ce influențează cel mai mult scorul de credit?",
                [
                    ("a", "How much you earn", "Cât câștigi"),
                    ("b", "How much you keep in savings", "Câți bani ții în economii"),
                    ("c", "Whether you repay on time", "Dacă rambursezi la timp"),
                ],
                "c",
                "Payment history is the single largest factor.",
                "Istoricul plăților este factorul cel mai important.",
            ),
            _q(
                "credit-score-2",
                "After paying on time, what matters most?",
                "După plata la timp, ce contează cel mai mult?",
                [
                    ("a", "How much of your available credit you routinely use", "Cât din creditul disponibil folosești în mod obișnuit"),
                    ("b", "How many bank accounts you hold", "Câte conturi bancare ai"),
                    ("c", "Which bank you use", "La ce bancă ești"),
                ],
                "a",
                "Routinely using most of your available credit counts against you.",
                "Folosirea constantă a aproape întregului credit disponibil îți scade scorul.",
            ),
            _q(
                "credit-score-3",
                "Does a high salary guarantee a high credit score?",
                "Un salariu mare garantează un scor de credit mare?",
                [
                    ("a", "Yes, income is the main input", "Da, venitul este intrarea principală"),
                    ("b", "No, income is not what a score measures", "Nu, venitul nu este ce măsoară scorul"),
                    ("c", "Only above a certain salary", "Doar peste un anumit salariu"),
                ],
                "b",
                "Someone with a high salary and missed payments can score worse than a modest, punctual payer.",
                "Cineva cu salariu mare și plăți întârziate poate avea un scor mai slab decât un plătitor modest, dar punctual.",
            ),
            _q(
                "credit-score-4",
                "Does a longer credit history help?",
                "Un istoric de credit mai lung ajută?",
                [
                    ("a", "Yes", "Da"),
                    ("b", "No, only the last month counts", "Nu, contează doar ultima lună"),
                    ("c", "It lowers the score", "Scade scorul"),
                ],
                "a",
                "A longer record gives a lender more evidence to judge reliability on.",
                "Un istoric mai lung oferă creditorului mai multe dovezi pentru a evalua seriozitatea.",
            ),
            _q(
                "credit-score-5",
                "A credit score is fundamentally a measure of:",
                "Scorul de credit este, în esență, o măsură a:",
                [
                    ("a", "Wealth", "Averii"),
                    ("b", "Repayment reliability", "Seriozității în rambursare"),
                    ("c", "Spending habits", "Obiceiurilor de cheltuire"),
                ],
                "b",
                "It summarises how reliably you have repaid borrowed money, nothing more.",
                "Rezumă cât de constant ai rambursat banii împrumutați, nimic mai mult.",
            ),
        ),
    ),
    Lesson(
        id="current-vs-savings",
        title_en="Current account vs savings account",
        title_ro="Cont curent vs cont de economii",
        body_en=(
            "A current account is built for movement: salary in, card payments and transfers out, "
            "no meaningful interest. A savings account is built for stillness: fewer movements, "
            "some interest, and just enough friction that you do not spend the balance by "
            "accident. Keeping the two apart is what makes saving work — money you have to "
            "deliberately move back is money you are far less likely to spend. "
            "In practice the split works best when the money moves on payday rather than at the end "
            "of the month, because what is left at the end is usually nothing. A standing order the "
            "day after your salary lands turns saving into something that happens without a "
            "decision, and what remains in the current account is then genuinely yours to spend."
        ),
        body_ro=(
            "Contul curent este făcut pentru mișcare: salariul intră, plățile cu cardul și "
            "transferurile ies, fără dobândă semnificativă. Contul de economii este făcut pentru "
            "liniște: mai puține mișcări, o oarecare dobândă și exact atâta fricțiune cât să nu "
            "cheltuiești soldul din greșeală. Separarea celor două este ceea ce face economisirea "
            "să funcționeze — banii pe care trebuie să îi muți înapoi în mod deliberat sunt bani "
            "pe care e mult mai puțin probabil să îi cheltuiești. "
            "În practică, separarea funcționează cel mai bine când banii se mută în ziua "
            "salariului, nu la sfârșitul lunii, pentru că la sfârșit de obicei nu mai rămâne nimic. "
            "Un ordin de plată programat a doua zi după intrarea salariului transformă economisirea "
            "într-un lucru care se întâmplă fără decizie, iar ce rămâne în contul curent devine cu "
            "adevărat al tău, de cheltuit."
        ),
        questions=(
            _q(
                "current-savings-1",
                "A current account is built for:",
                "Contul curent este făcut pentru:",
                [
                    ("a", "Movement: salary in, payments out", "Mișcare: salariul intră, plățile ies"),
                    ("b", "Stillness and interest", "Liniște și dobândă"),
                    ("c", "Long-term investing", "Investiții pe termen lung"),
                ],
                "a",
                "It is the account your day-to-day money flows through.",
                "Este contul prin care curg banii de zi cu zi.",
            ),
            _q(
                "current-savings-2",
                "A savings account is built for:",
                "Contul de economii este făcut pentru:",
                [
                    ("a", "Frequent card payments", "Plăți frecvente cu cardul"),
                    ("b", "Fewer movements and some interest", "Mai puține mișcări și o oarecare dobândă"),
                    ("c", "Receiving your salary", "Primirea salariului"),
                ],
                "b",
                "Stillness is the point: fewer movements, some interest, a little friction.",
                "Liniștea e ideea: mai puține mișcări, ceva dobândă, puțină fricțiune.",
            ),
            _q(
                "current-savings-3",
                "Why keep savings in a separate account?",
                "De ce să ții economiile într-un cont separat?",
                [
                    ("a", "The friction of moving it back makes it less likely to be spent", "Fricțiunea de a-i muta înapoi îi face mai puțin probabil de cheltuit"),
                    ("b", "Current accounts have a legal maximum balance", "Conturile curente au un sold maxim legal"),
                    ("c", "Savings cannot be accessed until a fixed date", "Economiile nu pot fi accesate până la o dată fixă"),
                ],
                "a",
                "Separation is behavioural, not legal. It protects the balance from accidental spending.",
                "Separarea este comportamentală, nu legală. Protejează soldul de cheltuieli accidentale.",
            ),
            _q(
                "current-savings-4",
                "Which typically pays meaningful interest?",
                "Care plătește de obicei dobândă semnificativă?",
                [
                    ("a", "The current account", "Contul curent"),
                    ("b", "The savings account", "Contul de economii"),
                    ("c", "Neither ever does", "Niciunul, niciodată"),
                ],
                "b",
                "A current account pays little or nothing; interest is part of what a savings account is for.",
                "Contul curent plătește puțin sau deloc; dobânda face parte din rostul contului de economii.",
            ),
            _q(
                "current-savings-5",
                "Your salary and card payments belong in:",
                "Salariul și plățile cu cardul aparțin în:",
                [
                    ("a", "The savings account", "Contul de economii"),
                    ("b", "The current account", "Contul curent"),
                    ("c", "Whichever has the higher balance", "Cel cu soldul mai mare"),
                ],
                "b",
                "Day-to-day movement belongs in the account designed for movement.",
                "Mișcarea de zi cu zi aparține contului proiectat pentru mișcare.",
            ),
        ),
    ),
    Lesson(
        id="inflation",
        title_en="Why inflation matters to savers",
        title_ro="De ce contează inflația pentru cei care economisesc",
        body_en=(
            "Inflation is the rate at which prices rise, which means the same amount of money "
            "buys a little less each year. Money sitting in an account earning less than "
            "inflation is quietly losing purchasing power even though the number on the screen "
            "never falls. This is why an emergency fund is sized in months of expenses rather "
            "than in a fixed sum decided years ago. "
            "The number worth watching is the difference between the interest you earn and the rate "
            "prices rise at: if a deposit pays 5% while inflation runs at 7%, your money loses "
            "about 2% a year in what it can actually buy. That is not an argument for holding no "
            "cash — it is an argument for keeping the amount you genuinely need close at hand, and "
            "not much more than that sitting idle."
        ),
        body_ro=(
            "Inflația este ritmul în care cresc prețurile, ceea ce înseamnă că aceeași sumă "
            "cumpără puțin mai puțin în fiecare an. Banii care stau într-un cont cu o dobândă mai "
            "mică decât inflația pierd discret putere de cumpărare, chiar dacă numărul de pe "
            "ecran nu scade niciodată. De aceea un fond de urgență se măsoară în luni de "
            "cheltuieli, nu într-o sumă fixă stabilită acum câțiva ani. "
            "Cifra care contează este diferența dintre dobânda pe care o încasezi și ritmul în care "
            "cresc prețurile: dacă un depozit dă 5% în timp ce inflația este 7%, banii tăi pierd "
            "aproximativ 2% pe an din ce pot cumpăra efectiv. Asta nu înseamnă că nu trebuie să ții "
            "deloc bani lichizi — înseamnă doar să ții la îndemână suma de care chiar ai nevoie și "
            "să nu lași mult peste ea nefolosită."
        ),
        questions=(
            _q(
                "inflation-1",
                "Inflation is:",
                "Inflația este:",
                [
                    ("a", "The rate at which prices rise", "Ritmul în care cresc prețurile"),
                    ("b", "The interest a bank pays you", "Dobânda pe care ți-o plătește banca"),
                    ("c", "A tax on savings", "O taxă pe economii"),
                ],
                "a",
                "Rising prices mean the same money buys a little less each year.",
                "Prețurile în creștere înseamnă că aceiași bani cumpără puțin mai puțin în fiecare an.",
            ),
            _q(
                "inflation-2",
                "Money in an account earning less than inflation is:",
                "Banii dintr-un cont cu dobândă mai mică decât inflația:",
                [
                    ("a", "Losing purchasing power", "Pierd putere de cumpărare"),
                    ("b", "Gaining purchasing power", "Câștigă putere de cumpărare"),
                    ("c", "Unaffected", "Nu sunt afectați"),
                ],
                "a",
                "The balance buys less over time even though it never shrinks.",
                "Soldul cumpără tot mai puțin, chiar dacă nu scade niciodată.",
            ),
            _q(
                "inflation-3",
                "Does the number on your screen fall when inflation erodes your savings?",
                "Scade numărul de pe ecran când inflația îți erodează economiile?",
                [
                    ("a", "Yes, the balance drops", "Da, soldul scade"),
                    ("b", "No, which is why the loss is easy to miss", "Nu, de aceea pierderea trece ușor neobservată"),
                    ("c", "Only in a savings account", "Doar într-un cont de economii"),
                ],
                "b",
                "The loss is invisible on the statement, which is exactly what makes it easy to ignore.",
                "Pierderea este invizibilă pe extras, exact de aceea e ușor de ignorat.",
            ),
            _q(
                "inflation-4",
                "Inflation is 5% and your account pays 2%. Your real return is:",
                "Inflația este 5%, iar contul îți plătește 2%. Randamentul real este:",
                [
                    ("a", "Positive", "Pozitiv"),
                    ("b", "Zero", "Zero"),
                    ("c", "Negative", "Negativ"),
                ],
                "c",
                "Earning less than inflation means going backwards in real terms.",
                "O dobândă sub inflație înseamnă că, în termeni reali, dai înapoi.",
            ),
            _q(
                "inflation-5",
                "Why size an emergency fund in months of expenses?",
                "De ce să dimensionezi fondul de urgență în luni de cheltuieli?",
                [
                    ("a", "So it tracks rising costs automatically", "Ca să urmărească automat costurile în creștere"),
                    ("b", "Because banks require it", "Pentru că băncile cer asta"),
                    ("c", "To make it easier to calculate", "Ca să fie mai ușor de calculat"),
                ],
                "a",
                "A sum fixed years ago silently becomes too small as prices rise.",
                "O sumă fixată acum câțiva ani devine discret prea mică pe măsură ce prețurile cresc.",
            ),
        ),
    ),
    Lesson(
        id="debt-payoff-order",
        title_en="Which debt to clear first",
        title_ro="Ce datorie să achiți prima",
        body_en=(
            "When several debts compete for the same money, pay the minimum on all of them and "
            "put everything left over against the one with the highest interest rate. That costs "
            "the least in total. Some people instead clear the smallest balance first for the "
            "motivation of finishing something — slightly more expensive, but a plan you "
            "actually stick to beats a cheaper one you abandon. "
            "Before choosing between the two, write down every debt with its balance, its interest "
            "rate and its minimum payment; the right order usually becomes obvious once they sit "
            "side by side. And whichever order you pick, avoid taking on new debt while you work "
            "through the list — otherwise you are paying one balance down while quietly building "
            "another."
        ),
        body_ro=(
            "Când mai multe datorii concurează pentru aceiași bani, plătește minimul la toate și "
            "pune tot ce rămâne pe cea cu cea mai mare dobândă. Așa plătești cel mai puțin în "
            "total. Unii preferă să achite întâi soldul cel mai mic, pentru motivația de a "
            "termina ceva — puțin mai scump, dar un plan pe care chiar îl respecți bate unul mai "
            "ieftin pe care îl abandonezi. "
            "Înainte să alegi între cele două, notează fiecare datorie cu soldul, dobânda și plata "
            "minimă; ordinea potrivită devine de obicei evidentă abia când le vezi una lângă alta. "
            "Și indiferent ce ordine alegi, evită să iei datorii noi cât timp parcurgi lista — "
            "altfel plătești un sold în timp ce, discret, construiești altul."
        ),
        questions=(
            _q(
                "debt-1",
                "Which approach costs the least in total interest?",
                "Ce abordare costă cel mai puțin în dobândă totală?",
                [
                    ("a", "Clearing the smallest balance first", "Achitarea întâi a soldului cel mai mic"),
                    ("b", "Minimum on all, extra against the highest rate", "Minimul la toate, restul la dobânda cea mai mare"),
                    ("c", "Splitting spare money equally", "Împărțirea egală a banilor rămași"),
                ],
                "b",
                "Attacking the highest rate first minimises what the debt costs overall.",
                "Atacarea celei mai mari dobânzi minimizează cât te costă datoria în total.",
            ),
            _q(
                "debt-2",
                "Clearing the smallest balance first is mainly about:",
                "Achitarea întâi a soldului cel mai mic ține mai ales de:",
                [
                    ("a", "Motivation", "Motivație"),
                    ("b", "Paying less interest", "Plata unei dobânzi mai mici"),
                    ("c", "A legal requirement", "O cerință legală"),
                ],
                "a",
                "It is slightly more expensive, but finishing something keeps people going.",
                "Este puțin mai scump, dar senzația că ai terminat ceva îi ține pe oameni în ritm.",
            ),
            _q(
                "debt-3",
                "Should you skip minimum payments on other debts to attack the highest rate?",
                "Ar trebui să sari peste plățile minime la celelalte datorii ca să ataci dobânda cea mai mare?",
                [
                    ("a", "Yes, put every leu on the highest rate", "Da, pune fiecare leu pe dobânda cea mai mare"),
                    ("b", "No, always pay the minimum on all of them", "Nu, plătește mereu minimul la toate"),
                    ("c", "Only if the other rates are low", "Doar dacă celelalte dobânzi sunt mici"),
                ],
                "b",
                "Missing a minimum triggers penalties and damages your payment history.",
                "Neplata minimului atrage penalități și îți strică istoricul de plăți.",
            ),
            _q(
                "debt-4",
                "You have debts at 8%, 19% and 24%. Spare money should go to:",
                "Ai datorii la 8%, 19% și 24%. Banii rămași ar trebui să meargă la:",
                [
                    ("a", "The 24% debt", "Datoria de 24%"),
                    ("b", "The 8% debt", "Datoria de 8%"),
                    ("c", "The largest balance", "Soldul cel mai mare"),
                ],
                "a",
                "The highest rate is the one costing you most for every leu still owed.",
                "Dobânda cea mai mare este cea care te costă cel mai mult pentru fiecare leu rămas.",
            ),
            _q(
                "debt-5",
                "The best debt plan is ultimately:",
                "Cel mai bun plan de rambursare este, în cele din urmă:",
                [
                    ("a", "The cheapest one on paper", "Cel mai ieftin pe hârtie"),
                    ("b", "One you will actually stick to", "Unul pe care chiar îl vei respecta"),
                    ("c", "The one your bank suggests", "Cel sugerat de bancă"),
                ],
                "b",
                "A cheaper plan you abandon costs more than a slightly dearer one you finish.",
                "Un plan mai ieftin pe care îl abandonezi costă mai mult decât unul puțin mai scump pe care îl duci la capăt.",
            ),
        ),
    ),
    Lesson(
        id="savings-goals",
        title_en="Turning a wish into a goal",
        title_ro="Cum transformi o dorință într-un obiectiv",
        body_en=(
            "Saving more is a wish; putting aside 12.000 RON for a car by December next year is a "
            "goal. A goal names an amount, a date and where the money comes from, which makes it "
            "possible to divide it into a weekly or monthly figure and notice early if you are "
            "behind. Automating that figure as a standing order removes the monthly decision "
            "entirely. "
            "An amount and a date also show early whether the plan is realistic: if the weekly "
            "figure is larger than what is genuinely left after your fixed costs, it is better to "
            "move the date or lower the target than to abandon the goal in month three. Several "
            "goals at once are fine as long as each has its own amount, date and account — what "
            "does not work is one vague pot everything is supposed to come out of."
        ),
        body_ro=(
            "Să economisești mai mult este o dorință; să pui deoparte 12.000 RON pentru o mașină "
            "până în decembrie anul viitor este un obiectiv. Un obiectiv numește o sumă, o dată "
            "și sursa banilor, ceea ce face posibilă împărțirea lui într-o cifră săptămânală sau "
            "lunară și observarea din timp dacă ai rămas în urmă. Automatizarea acelei cifre "
            "printr-un ordin de plată programat elimină complet decizia lunară. "
            "O sumă și o dată îți arată din timp și dacă planul este realist: dacă cifra "
            "săptămânală este mai mare decât ce rămâne cu adevărat după costurile fixe, e mai bine "
            "să muți data sau să cobori ținta decât să abandonezi obiectivul în luna a treia. Mai "
            "multe obiective în paralel sunt în regulă, atâta timp cât fiecare are suma, data și "
            "contul lui — ce nu funcționează este un singur borcan vag din care se presupune că "
            "iese totul."
        ),
        questions=(
            _q(
                "goals-1",
                "Which of these is a goal rather than a wish?",
                "Care dintre acestea este un obiectiv, nu o dorință?",
                [
                    ("a", "I should save more", "Ar trebui să economisesc mai mult"),
                    ("b", "12.000 RON for a car by next December", "12.000 RON pentru o mașină până în decembrie anul viitor"),
                    ("c", "I want to be better with money", "Vreau să mă descurc mai bine cu banii"),
                ],
                "b",
                "An amount and a date are what turn an intention into something you can track.",
                "O sumă și o dată transformă o intenție în ceva ce poți urmări.",
            ),
            _q(
                "goals-2",
                "A well-formed goal names:",
                "Un obiectiv bine formulat numește:",
                [
                    ("a", "An amount, a date and where the money comes from", "O sumă, o dată și sursa banilor"),
                    ("b", "Only the amount", "Doar suma"),
                    ("c", "Only the reason you want it", "Doar motivul pentru care îl vrei"),
                ],
                "a",
                "All three are needed before you can turn it into a weekly or monthly figure.",
                "Toate trei sunt necesare ca să îl poți transforma într-o cifră săptămânală sau lunară.",
            ),
            _q(
                "goals-3",
                "Why divide a goal into a weekly or monthly figure?",
                "De ce să împarți un obiectiv într-o cifră săptămânală sau lunară?",
                [
                    ("a", "To notice early if you are falling behind", "Ca să observi din timp dacă rămâi în urmă"),
                    ("b", "Because banks require instalments", "Pentru că băncile cer rate"),
                    ("c", "To reduce the total amount needed", "Ca să reduci suma totală necesară"),
                ],
                "a",
                "A per-period figure turns a distant target into something you can check against.",
                "O cifră pe perioadă transformă o țintă îndepărtată în ceva ce poți verifica.",
            ),
            _q(
                "goals-4",
                "What does automating the contribution as a standing order remove?",
                "Ce elimină automatizarea contribuției printr-un ordin de plată programat?",
                [
                    ("a", "The monthly decision to save", "Decizia lunară de a economisi"),
                    ("b", "The need for a target date", "Nevoia unei date-țintă"),
                    ("c", "Any interest you would earn", "Orice dobândă ai câștiga"),
                ],
                "a",
                "Removing the decision is the point: saving stops depending on willpower each month.",
                "Eliminarea deciziei este ideea: economisirea nu mai depinde de voință în fiecare lună.",
            ),
            _q(
                "goals-5",
                "Saving more is best described as:",
                "A economisi mai mult este descris cel mai bine ca:",
                [
                    ("a", "A goal", "Un obiectiv"),
                    ("b", "A wish", "O dorință"),
                    ("c", "A budget", "Un buget"),
                ],
                "b",
                "Without an amount and a date there is nothing to measure progress against.",
                "Fără o sumă și o dată nu există nimic față de care să măsori progresul.",
            ),
        ),
    ),
]


@lru_cache(maxsize=1)
def load_lessons() -> list[Lesson]:
    return list(_LESSONS)
