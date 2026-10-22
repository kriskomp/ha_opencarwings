# Zmiany

Numeracja wersji: `RRRR.MM.DD.N` (data wydania i numer kolejnego PR danego dnia, jak w ha-solaredge-v2). Wydanie na GitHubie powstaje automatycznie po zmianie wersji w
`custom_components/ha_opencarwings/manifest.json` na gałęzi `main`, a jego opis to odpowiednia sekcja tego pliku.
Poprzednie wydanie (1.0.0, bez wersjonowania datą) to kod z [oryginału developerfromjokela/ha_opencarwings](https://github.com/developerfromjokela/ha_opencarwings)
(commit „Fix some issues” z 29.08.2026).

## 2026.10.22.1

- **Bez czekania na timeout serwera.** Nowa opcja „Zapytaj ponownie po N sekundach bez odpowiedzi” (30–900, domyślnie
  300 = timeout serwera; wpisz np. 120, żeby ponawiać szybciej). „Refresh data” bez odpowiedzi auta przez ten czas jest
  wysyłane jeszcze raz (jedna ponowna próba; serwer przyjmuje nową komendę, gdy poprzednia czeka). Dotyczy przycisku „Request data refresh”,
  odświeżania podczas ładowania i sprawdzania zaparkowanego auta. Odświeżenie czekające dłużej niż ustawiony czas nie
  blokuje już następnego cyklu (wcześniej do 5+ minut bez danych o baterii podczas ładowania). Inne komendy (A/C,
  drzwi) nie są powtarzane. `LEAF_COMMAND_TIMEOUT` to ustawienie serwera, integracja go nie zmienia.
- **„Jedzie” bez potwierdzenia.** Serwer czyści `car_running` dopiero po pakiecie z auta z wyłączonym zapłonem; gdy
  raport końca podróży nie dotrze (np. brak zgody na ekranie navi), auto „jedzie” godzinami. Gdy `car_running` jest
  włączone, a ostatni pakiet danych jest starszy niż N minut (nowa opcja „„Jedzie” bez potwierdzenia po N minutach”,
  5–240, domyślnie 20), sensor Status pokazuje `idle` z atrybutem
  `driving_unconfirmed: true` (zmienia się tylko wyświetlanie w HA). Sprawdzanie zaparkowanego auta nie jest już blokowane przez taki nieaktualny stan.
- **Nowa opcja „Pytaj auto, które wygląda na jadące, co N minut”** (wyłączona; 5/10/15 min). Wysyła „Refresh data”,
  dopóki auto nie odpowie, że stoi (poprawia to też stan na serwerze, stronie i w aplikacji). Po 3 pytaniach bez
  odpowiedzi z rzędu robi pauzę do czasu, aż auto samo coś wyśle (akumulator 12 V zaparkowanego auta się nie ładuje).
- README: nowe sekcje o niepotwierdzonym odświeżeniu i o „jedzie” bez końca.

Wnioski z danych (dwa zrzuty stanów): ostatni pakiet `ev_info` miał faktycznie `ignition=true` (odpowiedź na odświeżenie
w czasie jazdy), a po zaparkowaniu auto nie połączyło się z serwerem wcale (`last_connection` bez zmian). Do sprawdzenia
po wdrożeniu: czy odpowiedź zaparkowanego auta na „Refresh data” faktycznie czyści „jedzie” na serwerze.

## 2026.10.21.8

Porządki po przejściu na WebSocket: mniej zbędnych encji, sterowanie A/C jak w aplikacji, wznawianie połączenia.

- **Usunięte:** przycisk konta „OpenCARWINGS Refresh” i bezimienne urządzenie „Brak nazwy”, usługa `ha_opencarwings.refresh`,
  sensor „Last Requested”, sensor listy aut, martwy sensor Vehicle Health Report. Stare encje znikają same przy starcie.
  „Poproś auto o dane” zostaje tylko przy każdym aucie.
- **Zapasowy odczyt REST** przy działającym WebSocket: co 30 min (było 60).
- **Przełącznik A/C pokazuje prawdziwy stan** (`ac_status` z WebSocket). Po kliknięciu zostaje w wybranej pozycji, dopóki
  auto nie odpowie (alerty 4/5/7), komenda się nie powiedzie (błąd/timeout, alert 97 – powiadomienie i powrót do stanu auta)
  albo nie minie 15 min. Gdy auto przez 15 min nic nie wyśle, wysyłane jest jedno „Refresh data”.
- **Nowy suwak „A/C Temperature”** (16–31 °C, domyślnie 21, pamiętany po restarcie; tylko TCU `ficosa2016`). HA przelicza na °F,
  na serwer zawsze idą stopnie Celsjusza.
- **Ponowne połączenie:** diagnostyczny przycisk „Reconnect live updates” i sensor „Push Connection” (po jednym na konto,
  przy pierwszym aucie) oraz zgłoszenie w Naprawach po 10 min bez połączenia z akcją „Połącz ponownie” (znika samo po powrocie połączenia).
- **Ikony** z Material Design Icons dla przycisków i przełącznika; sensory „6.6 kW OBC Exists” i „Battery Heater Exists” są diagnostyczne.
- **Identyfikatory przycisków drzwi** (`entity_id`) są dopasowane do akcji: komenda 7 = `…unlock_doors…`, 8 = `…lock_doors…`.
  Zaktualizuj automatyzacje, które używały starych identyfikatorów.
- `raw_car` nie jest zapisywany w bazie recordera.
- README: opis zmian, przykładowa karta Lovelace, lista TODO z audytu aplikacji.

Do sprawdzenia na żywym serwerze: po jakim czasie auto raportuje `ac_status` po włączeniu A/C oraz czy serwer produkcyjny ma ten sam limit 31 °C.

## 2026.10.21.7

- **Nowa opcja „Sprawdzaj zaparkowane auto co N godzin/dni”** (wyłączona; 6 h, 12 h, 1 dzień, 2, 3 dni, tydzień,
  2 tygodnie). Zaparkowane auto samo nic nie wysyła, więc integracja po tak długiej ciszy wysyła „Refresh data”
  (komenda budzi modem auta). Zasady (jak okresowe odświeżanie na serwerze OpenCARWINGS, które API pozwala tylko
  odczytać): tylko gdy auto milczy cały interwał (brak pakietu danych i połączenia), nie ładuje się ani nie jedzie,
  nie ma komendy w toku i w ostatnim interwale nie poproszono o żadną komendę. Ostatnia zasada chroni akumulator 12 V:
  auto, które nie odpowiedziało (timeout, błąd), nie jest budzone ponownie przed upływem pełnego interwału, także po
  restarcie HA. Sprawdzenie działa co 30 minut na danych, które integracja już ma.
- **Przełącznik A/C nie szarzeje bez powodu.** Przełącznik trzymał obiekt auta z chwili uruchomienia i nigdy go nie
  odświeżał, a w .6 dodatkowo był niedostępny, gdy jakaś komenda była w toku (np. odświeżenie czekające na
  odpowiedź uśpionego auta). Teraz przełącznik czyta bieżące dane koordynatora (jak pozostałe encje) i jest
  niedostępny wyłącznie wtedy, gdy auto nie obsługuje A/C (`supported_commands` bez komend 3 i 4).

## 2026.10.21.6

Poprawki wydania .5 (zostało scalone, zanim te zmiany do niego trafiły).

- **Ważne: zamek i odblokowanie miały zamienione nazwy.** Na serwerze komenda 7 to „Door unlock”, a 8 to „Door lock”.
  W .5 przycisk komendy 7 nazywał się „Lock Doors” i w rzeczywistości odblokowywał auto. Teraz: komenda 7 =
  „Unlock Doors”, komenda 8 = „Lock Doors”. `entity_id` i unikalne identyfikatory się nie zmieniają (są historycznie
  zamienione: `…doorlock…` wysyła odblokowanie).
- **Czasy jako tekst „4 h 52 min”** (3 kW, 1 kW, 6,6 kW i „Data Age”) zamiast liczb z jednostką: HA miał zapamiętaną
  jednostkę „s” i pokazywał np. „17 520,00 s”, a serwer podaje minuty. Liczba minut jest w atrybucie `minutes`.
  Te cztery encje nie są już liczbowe (bez jednostki i klasy `duration`).
- **Przyciski pasują do auta.** Sprawdzenie obsługi komend nigdy nie działało (kod ustawiał własną właściwość
  `is_available`, której HA nie czyta), więc pokazywały się wszystkie przyciski. Teraz integracja czyta z API
  `supported_commands` (zależy od typu TCU): przyciski nieobsługiwanych komend nie są tworzone, a ich stare encje są
  usuwane z rejestru (Leaf z TCU `ficosa2016` nie ma „Charge start 80%”). Brak listy w odpowiedzi API oznacza
  „obsługiwane”. Przełącznik A/C jest niedostępny, gdy komenda trwa albo auto nie obsługuje A/C.
- **Mapa:** panel „Mapa” HA nie pokazuje encji w stanie `home`, więc auto stojące w strefie „Dom” widać dopiero na
  karcie mapy z jawnie wpisanym trackerem (`label_mode: icon`); w drodze pokazuje je też panel „Mapa”. Poprawiony
  błędny opis z .5 („znacznik przykryty przez osoby”).
- **README uporządkowany pod nowego użytkownika:** konfiguracja opisuje token API (pole „API-key” na stronie
  OpenCARWINGS), tabela opcji z ustawieniami domyślnymi, usługa i zdarzenie, uwaga o mapie, poprawione wzorce
  wykluczeń recordera i tabela unikalnych identyfikatorów.

## 2026.10.21.5

- **Daty jako natywny `timestamp`.** „Last Requested” zwracał tekst (`2026-10-21T08:59:13.106914Z`), teraz ma klasę
  `timestamp` (HA pokazuje „x minut temu” w czasie lokalnym); przed pierwszym odczytem jest `unknown`, bez błędów
  konwersji. „Data Age” ma klasę `duration` (minuty). Atrybuty tekstowe z datami zostają w formacie `dd.mm.rrrr gg:mm`.
- **Czasy ładowania (3 kW, 1 kW, 6,6 kW)** miały jednostkę „s”, a serwer podaje minuty (np. 292 = 4 h 52 min);
  jednostka to teraz `min`.
- **Tracker auta ma ikonę `mdi:car`** (opis przykrycia znacznika jest błędny, patrz .6), żeby na mapie dało się go odróżnić od osób. Gdy auto stoi w strefie
  „Dom”, jego znacznik leży kilka metrów od znaczników osób i może być przez nie przykryty; współrzędne są te same
  co w panelu OpenCARWINGS.
- **(błędne, poprawione w .6)** **Przycisk „Lock Doors”** (komenda 7) nazywał się „Unlock Doors”, tak samo jak przycisk odblokowania.
  Nazwa jest poprawiona; istniejące encje zachowują swoje `entity_id`, więc nic nie trzeba kasować.

## 2026.10.21.4

- **Opcja „Pokazuj auto na mapie (device tracker)”** (Konfiguruj; domyślnie włączona, czyli bez zmiany dla
  istniejących instalacji). Wyłączona: encja device tracker nie jest tworzona, a istniejąca jest usuwana z
  rejestru encji przy przeładowaniu; pozycja znika też z atrybutu `raw_car` sensora `Status`. Włączona: auto
  widać na mapie.
- **Tracker teraz się porusza.** Trzymał obiekt auta z chwili uruchomienia, a koordynator przy każdym odczycie
  podmienia obiekty, więc pozycja nigdy się nie aktualizowała. Tracker czyta teraz bieżące dane koordynatora
  (jak pozostałe encje). Atrybuty trackera mają `last_updated` (czas pozycji, `dd.mm.rrrr gg:mm`); brak pozycji
  nie powoduje już błędu.
- Razem z WebSocket (2026.10.21.3) pozycja na mapie zmienia się od razu po zdarzeniu `location` z serwera.
- **Testy:** opcja (wł./wył., sprzątanie rejestru), śledzenie koordynatora, atrybuty, ukrywanie pozycji w `raw_car`.

## 2026.10.21.3

- **Aktualizacje na żywo przez WebSocket** (`/ws/notif/`, ten sam token API co w REST, bez loginu i hasła).
  Serwer wysyła pełny stan auta przy każdym pakiecie z auta, zmianie lokalizacji, konfiguracji i wyniku komendy,
  więc „Data Age”, „Command Status” i reszta encji zmieniają się od razu. Opcja „Aktualizacje na żywo (WebSocket)”
  w *Konfiguruj* (domyślnie włączona); `iot_class` zmieniony na `cloud_push`.
- **Ograniczenia WebSocket obsłużone w kodzie:**
  - brak odtwarzania zdarzeń → po każdym (ponownym) połączeniu pełny odczyt przez REST, a odpytywanie działa
    dalej jako wolna siatka bezpieczeństwa (1 godzina lub ustawiony interwał, co dłuższe); po rozłączeniu wraca
    zwykły interwał,
  - brak pinga aplikacyjnego → heartbeat 30 s i ponowne łączenie z rosnącym opóźnieniem (5 s … 5 min),
  - serwer zamyka połączenie przy złym tokenie → odrzucony handshake (401/403) lub trzy zamknięcia przed
    komunikatem `listen` to błąd uwierzytelnienia: bez szybkiej pętli ponowień, ponowna próba co godzinę
    i prośba o nowy token (nowy krok *reauth*),
  - WebSocket nie wymusza nowych danych → komenda „Refresh data” nadal potrzebna; jej wynik przychodzi
    od razu, a śledzenie komendy odpytuje 4x rzadziej, gdy socket działa.
- Z README usunięta pozycja „Implement WebSockets client” z listy To-Do (zrobione).
- Nowa encja diagnostyczna „Push Connection” (binary_sensor) oraz zdarzenie `ha_opencarwings_alert` dla
  komunikatów `alert` z serwera.

## 2026.10.21.2

- **Skąd wiadomo, że dane pochodzą z auta.** Sensory „Last Updated” i atrybuty `last_connection` / `last_evinfo` /
  `raw_car` zawsze pokazywały pustkę. Przyczyna: klient API oznacza `ev_info.last_updated`, `last_connection`
  i `command_request_time` jako pola tylko do odczytu, a `to_dict()` takie pola pomija. Integracja czyta teraz
  te pola bezpośrednio z modelu. `ev_info.last_updated` ustawia serwer za każdym razem, gdy z auta przyjdzie
  pakiet z danymi, więc to jest realny wiek danych z auta (nie z pamięci serwera).
- **Nowe encje (diagnostyczne, na każde auto):**
  - `Data Age` – minuty od ostatniego pakietu z auta, odświeżane co minutę,
  - `Data Fresh` (binary_sensor) – włączony, gdy dane nie są starsze niż próg (domyślnie 30 min),
  - `Command Status` – wynik ostatniej komendy: `waiting` / `success` / `error` / `timeout`, z atrybutem
    `last_confirmed_refresh` (kiedy auto ostatnio potwierdziło odświeżenie),
  - `Last Updated` ma teraz klasę `timestamp` (wcześniej tekst ISO lub „unknown”).
- **Odświeżanie w czasie ładowania** (Konfiguruj → „Pytaj auto o dane co N minut w czasie ładowania”: wyłączone /
  5 / 10 / 15 / 30 min; domyślnie wyłączone). REST API nie pozwala ustawić `periodic_refresh` po stronie serwera,
  więc robi to integracja: co N minut wysyła komendę „Refresh data”, ale tylko gdy ostatni znany stan auta to
  ładowanie, nie ma oczekującej komendy, od poprzedniej minęło N minut, a dane nie są młodsze niż N/2
  (np. odświeżył je Twój skrypt). Dzięki temu można zrezygnować z własnej pętli odświeżania.
- **Przyciski i przełącznik A/C** po wysłaniu komendy śledzą ją aż do wyniku (odczyt co 15 s, do 8 min), więc
  `Command Status` i wiek danych aktualizują się same. Wcześniej aktualizacja kodu po komendzie nigdy się nie
  wykonywała (porównywano VIN z listą obiektów, a wywoływana metoda nie istnieje).
- **Opcje integracji działają.** `async_get_options_flow` było funkcją na poziomie modułu, więc Home Assistant
  nigdy nie pokazywał „Konfiguruj”; token z opcji był zapisywany pod kluczem, którego nikt nie czytał, a wartości
  wybierane z listy wracały jako tekst (`timedelta(minutes="15")` kończyłoby się błędem). Zmiana opcji przeładowuje
  integrację. Dodane tłumaczenia (en, pl).
- **README bez treści właściciela oryginału:** usunięte prośba o wsparcie (BuyMeACoffee), plakietki forum i aktywności,
  zgłaszanie błędów na jego repozytorium i odwołania do jego konta. Zostaje informacja, że kod pochodzi z
  developerfromjokela/ha_opencarwings, którego autor stworzył też serwer OpenCARWINGS.
- **Usunięte pliki Dockera** (`Dockerfile`, `.dockerignore`, `run_tests_in_docker.*`): obraz oparty o Pythona 3.11
  nie uruchomiłby obecnego kodu (składnia z 3.12) i instalował tylko `pytest`. Testy uruchamia GitHub Actions.
- **Licencja GPL-2.0** (plik `LICENSE`, ten sam tekst co w serwerze OpenCARWINGS) – walidacja HACS wymaga licencji.
  Oryginalne repozytorium nie ma żadnej, więc dobrze byłoby potwierdzić to z jego autorem.
- **Testy:** nowe testy dla wieku danych, wyboru momentu odświeżenia, śledzenia komend, encji, opcji i konfiguracji.

## 2026.10.21.1

- **Kod zgodny z działającą instalacją.** Do repozytorium trafiły dwie rzeczy, które do tej pory istniały tylko
  w Home Assistant autora forka:
  - `services.yaml` z opisem usługi `ha_opencarwings.refresh` (po polsku, z polem `entry_id`) – sama usługa
    była już w kodzie, brakowało jej opisu w interfejsie,
  - `manifest.json`: wymaganie `opencarwings_client@git+…` (z nazwą pakietu) zamiast samego adresu git,
    żeby pip poprawnie rozpoznawał pakiet.
- **Logo:** ikona integracji (`brand/icon.png`, `icon@2x.png`) to znak projektu OpenCARWINGS (`docs/public/favicon.svg` z
  [developerfromjokela/opencarwings](https://github.com/developerfromjokela/opencarwings), licencja GPL-2.0),
  zamiast napisu Nissan CARWINGS.
- `manifest.json` bez klucza `platforms`, którego Home Assistant nie zna, i z kluczami w kolejności wymaganej
  przez hassfest. Dodany właściciel kodu `@kriskomp`, dokumentacja wskazuje na ten fork.
- **Wydania automatyczne:** po zmianie wersji w `manifest.json` na `main` GitHub Actions uruchamia testy
  i publikuje wydanie z opisem z tego pliku (HACS pokaże ją jako aktualizację). Testy (Python 3.14) oraz
  walidacja HACS/hassfest działają przy każdym PR.
- **Testy:** zestaw odziedziczony z upstreamu nie dawał się uruchomić (pisany pod stary model danych: 39 z 44
  testów padało, a plik testu konfiguracji nie dawał się nawet zaimportować). Test konfiguracji przepisany pod
  obecny przepływ z tokenem, resztę przeniesiono do `tests/stale/` (nie jest uruchamiana, zostaje jako materiał
  referencyjny). Nowe testy powstają razem ze zmianami w kodzie.
