# Zmiany

Numeracja wersji: `RRRR.MM.DD.N` (data wydania i numer kolejnego PR danego dnia, jak w ha-solaredge-v2). Wydanie na GitHubie powstaje automatycznie po zmianie wersji w
`custom_components/ha_opencarwings/manifest.json` na gałęzi `main`, a jego opis to odpowiednia sekcja tego pliku.
Poprzednie wydanie (1.0.0, bez wersjonowania datą) to kod z [oryginału developerfromjokela/ha_opencarwings](https://github.com/developerfromjokela/ha_opencarwings)
(commit „Fix some issues” z 29.08.2026).

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
