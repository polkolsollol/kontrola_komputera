# kontrola_komputera

Aplikacja przesyla obraz ekranu z jednego komputera na drugi w sieci lokalnej.

Projekt dziala w modelu:

- `sender.py` - uruchamiany na komputerze, z ktorego ma byc wysylany ekran,
- `receiver.py` - uruchamiany na komputerze, ktory ma ten ekran odebrac i pokazac w oknie.

Po stronie nadawcy obraz ekranu jest przechwytywany, kompresowany do JPEG i wysylany przez TCP. Po stronie odbiorcy klatki sa odbierane i wyswietlane w interfejsie PySide6. Dodatkowo administrator po stronie receivera moze wyslac komendy `lock` i `unlock`, ktore wlaczaja albo wylaczaja blokade ekranu klienta.

## Architektura

Przeplyw danych:

```text
Komputer nadawcy
ScreenGrabber -> FrameData(JPEG) -> NetworkServer

Siec lokalna
TCP + prosty naglowek [payload_size][message_type]

Komputer odbiorcy
NetworkReceiver -> NetworkFrameProvider -> FrameWorker -> UI

Komendy administratora
UI -> MSG_TYPE_COMMAND(lock/unlock) -> sender -> blokada/odblokowanie ekranu klienta
```

Najwazniejsze pliki:

- [sender.py](/C:/Users/Damian%20G/Documents/GitHub/kontrola_komputera/sender.py) - skrypt startowy nadajnika
- [receiver.py](/C:/Users/Damian%20G/Documents/GitHub/kontrola_komputera/receiver.py) - skrypt startowy odbiornika z UI
- [main.py](/C:/Users/Damian%20G/Documents/GitHub/kontrola_komputera/main.py) - opcjonalny launcher wygodny do lokalnych testow
- [grabber/screen_grabber.py](/C:/Users/Damian%20G/Documents/GitHub/kontrola_komputera/grabber/screen_grabber.py) - przechwytywanie ekranu
- [network/connection.py](/C:/Users/Damian%20G/Documents/GitHub/kontrola_komputera/network/connection.py) - transport TCP i serializacja klatek
- [ui/ui.py](/C:/Users/Damian%20G/Documents/GitHub/kontrola_komputera/ui/ui.py) - interfejs odbiornika
- [core/interfaces.py](/C:/Users/Damian%20G/Documents/GitHub/kontrola_komputera/core/interfaces.py) - wspolny kontrakt `FrameData` / `FrameProvider`

## Wymagania

- Windows
- Python 3.12+ albo zgodny interpreter z Twojego `venv`
- Dwa komputery w tej samej sieci lokalnej

Zaleznosci projektu sa w [requirements.txt](/C:/Users/Damian%20G/Documents/GitHub/kontrola_komputera/requirements.txt):

- `PySide6`
- `mss`
- `numpy`
- `opencv-python`
- `python-dotenv`

## Instalacja

W katalogu projektu uruchom:

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Jesli PowerShell blokuje aktywacje srodowiska:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Jak uruchomic program

### 1. Komputer nadawcy

Na komputerze, z ktorego chcesz wysylac ekran:

```powershell
python sender.py
```

Domyslnie skrypt:

- nasluchuje na `0.0.0.0:9000`,
- przechwytuje monitor `1`,
- wysyla okolo `15 FPS`,
- kompresuje obraz z jakoscia `75`.

Przyklad z wlasnymi ustawieniami:

```powershell
python sender.py --host 0.0.0.0 --port 9000 --monitor 1 --fps 20 --quality 80
```

Po uruchomieniu sender wypisze komunikat, ze czeka na polaczenie odbiornika.

Sender domyslnie probuje tez dodac sie do autostartu Windows. Jesli chcesz to pominac:

```powershell
python sender.py --no-autostart
```

### 2. Komputer odbiorcy

Na komputerze, na ktorym chcesz ogladac ekran:

```powershell
python receiver.py
```

Po otwarciu okna:

1. Wpisz adres IP komputera nadawcy.
2. Jesli sender korzysta z portu innego niz `9000`, wpisz adres w formacie `IP:PORT`.
3. Kliknij `Polacz`.

Przyklad adresu:

```text
192.168.1.100
```

albo:

```text
192.168.1.100:9000
```

Mozesz tez uruchomic odbiornik z gotowym adresem:

```powershell
python receiver.py --host 192.168.1.100 --port 9000
```

Albo od razu sprobowac polaczenia przy starcie:

```powershell
python receiver.py --host 192.168.1.100 --port 9000 --connect
```

## Jak poruszac sie w aplikacji odbiornika

Interfejs jest prosty i ma jeden glowny ekran:

- u gory znajduje sie pole `Adres nadawcy`,
- obok znajduja sie przyciski `Polacz` / `Rozlacz`, `Zablokuj ekran` i `Odblokuj ekran`,
- srodek okna pokazuje aktualny obraz z komputera nadawcy,
- na dole pasek statusu pokazuje stan polaczenia i FPS.

Znaczenie elementow:

- `Adres nadawcy` - IP komputera, na ktorym dziala `sender.py`
- `Polacz` - nawiazuje polaczenie i zaczyna odbior klatek
- `Rozlacz` - zatrzymuje odbior i rozlacza sesje
- `Zablokuj ekran` - wysyla do klienta polecenie wlaczenia blokady ekranu
- `Odblokuj ekran` - wysyla do klienta polecenie zdjecia blokady
- `Stan: Laczenie...` - aplikacja probuje polaczyc sie z nadajnikiem
- `Stan: Polaczono (...)` - odebrano pierwsze poprawne klatki
- `FPS` - liczba nowych klatek na sekunde wyswietlanych w UI

## Logowanie administratora

Receiver ma ekran logowania administratora. Dane sa czytane z pliku `.env` przez `python-dotenv`.

Obslugiwane zmienne:

- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

Jesli plik `.env` nie istnieje, aplikacja uzyje domyslnych danych:

```text
login: admin
haslo: admin
```

Przykladowy `.env`:

```text
ADMIN_USERNAME=admin
ADMIN_PASSWORD=moje_haslo
```

## Parametry skryptow

### sender.py

```powershell
python sender.py --help
```

Dostepne opcje:

- `--host` - adres nasluchu, domyslnie `0.0.0.0`
- `--port` - port TCP, domyslnie `9000`
- `--monitor` - indeks monitora dla biblioteki `mss`
- `--fps` - limit FPS przechwytywania
- `--quality` - jakosc JPEG od `1` do `100`
- `--no-autostart` - nie dodawaj sendera do autostartu Windows

### receiver.py

```powershell
python receiver.py --help
```

Dostepne opcje:

- `--host` - opcjonalny adres nadawcy wpisany od razu do UI
- `--port` - domyslny port TCP
- `--connect` - automatyczne polaczenie po uruchomieniu, jesli podano `--host`

## Dodatkowy launcher

Mozesz tez uruchamiac projekt przez [main.py](/C:/Users/Damian%20G/Documents/GitHub/kontrola_komputera/main.py):

```powershell
python main.py sender --port 9000
python main.py receiver --host 192.168.1.100 --connect
```

Ten plik jest tylko wygodnym wrapperem. Docelowo najczytelniej uzywac osobno `sender.py` i `receiver.py`.

## Typowy scenariusz krok po kroku

1. Na komputerze A uruchom `python sender.py`.
2. Sprawdz jego lokalny adres IPv4, np. `192.168.1.100`.
3. Na komputerze B uruchom `python receiver.py`.
4. Zaloguj sie jako administrator.
5. W polu `Adres nadawcy` wpisz `192.168.1.100`.
6. Kliknij `Polacz`.
7. Po chwili w oknie odbiornika powinien pojawic sie obraz z komputera A.
8. Jesli chcesz zablokowac ekran klienta, kliknij `Zablokuj ekran`.
9. Aby przywrocic normalny widok, kliknij `Odblokuj ekran`.

## Blokada ekranu klienta

Blokada dodana w projekcie jest blokada aplikacyjna, a nie natywnym ekranem logowania Windows.

To znaczy:

- sender tworzy topmost overlay na monitorach klienta,
- overlay mozna wlaczyc i wylaczyc z poziomu receivera,
- funkcja jest odwracalna przez administratora,
- nie zastępuje bezpiecznego `LockWorkStation()` i nie probuje obchodzic zabezpieczen systemu.

To podejscie jest praktyczne dla projektu szkolnego i sterowania administracyjnego, bo pozwala rowniez na zdalne odblokowanie.

## Autostart sendera w rejestrze

`sender.py` moze zapisac sie w autostarcie Windows przez [autostart_manager.py](/C:/Users/Damian%20G/Documents/GitHub/kontrola_komputera/autostart_manager.py).

Klucz rejestru:

```text
HKEY_CURRENT_USER\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run
```

Nazwa wartosci:

```text
SenderApp
```

Typ wartosci:

```text
REG_SZ
```

Dane wartosci:

- dla wersji `.exe`: sciezka do pliku wykonywalnego,
- dla wersji `.py`: komenda w postaci:

```text
"C:\\sciezka\\do\\python.exe" "C:\\sciezka\\do\\sender.py"
```

Jesli uruchamiasz sender z normalnego skryptu Pythona, to do rejestru nie trafia sama nazwa `sender.py`, tylko cala komenda potrzebna do jego odpalenia.

## Rozwiazywanie problemow

### Nie moge sie polaczyc

Sprawdz:

- czy oba komputery sa w tej samej sieci LAN,
- czy sender jest uruchomiony przed proba laczenia,
- czy wpisany adres IP jest poprawny,
- czy port po obu stronach jest taki sam,
- czy zapora systemowa Windows nie blokuje portu `9000`.

### Widze okno, ale brak obrazu

Sprawdz:

- czy sender rzeczywiscie przechwytuje poprawny monitor,
- czy monitor wskazany przez `--monitor` istnieje,
- czy `opencv-python`, `mss` i `numpy` sa zainstalowane,
- czy po stronie odbiorcy licznik `FPS` rosnie.

### Program dziala wolno

Mozesz zmniejszyc:

- `--fps`, zeby wysylac mniej klatek,
- `--quality`, zeby zmniejszyc rozmiar JPEG.

Przykladowo:

```powershell
python sender.py --fps 10 --quality 60
```

### Port 9000 jest zajety

Uruchom obie strony na innym porcie, na przyklad `9010`:

```powershell
python sender.py --port 9010
python receiver.py --host 192.168.1.100 --port 9010 --connect
```

## Test techniczny

W repo znajduje sie prosty test transportu:

```powershell
python test_network.py
```

Test uruchamia lokalny serwer i klient TCP oraz przesyla przykladowa klatke `FrameData`.

## Status projektu

Aktualna wersja spina wszystkie glowne obszary:

- przechwytywanie ekranu,
- kompresje JPEG,
- przesyl przez TCP,
- odbior i wyswietlanie w UI,
- zdalne komendy `lock` / `unlock`,
- dwa osobne skrypty startowe dla nadajnika i odbiornika.

To jest sensowna pierwsza wersja dzialajaca w LAN. Kolejne rozszerzenia mozna robic juz na spokojnie: autowybor monitorow, lepsze komunikaty o bledach, handshake protokolu, sterowanie zdalne, szyfrowanie albo obsluge wielu odbiornikow.
