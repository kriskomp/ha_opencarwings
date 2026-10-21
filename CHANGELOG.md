# Zmiany

Numeracja wersji: `RRRR.MM.DD.N` (data wydania i numer kolejnego PR danego dnia, jak w ha-solaredge-v2). Wydanie na GitHubie powstaje automatycznie po zmianie wersji w
`custom_components/ha_opencarwings/manifest.json` na gałęzi `main`, a jego opis to odpowiednia sekcja tego pliku.
Poprzednie wydanie (1.0.0, bez wersjonowania datą) to kod z [oryginału developerfromjokela/ha_opencarwings](https://github.com/developerfromjokela/ha_opencarwings)
(commit „Fix some issues” z 29.08.2026).

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
