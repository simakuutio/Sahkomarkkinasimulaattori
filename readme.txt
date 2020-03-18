Sähkömarkkinasimulaattori (MaSi)
---------------------------------

Käyttötarkoitus
===============
Sähkömarkkinasimulaattori (myöhemmin MaSi) on Fingrid Datahub Oy:lle
tuotettu työkalusetti testauksen avuksi jolla voidaan luoda ja
simuloida pienimuotoista sähkömarkkinaa käyttöpaikkoineen ja 
kulutuksineen. Työkalu on toteutettu Pythonilla ja se koostuu
muutamasta komponentista.

Ympäristövaatimukset
====================
MaSi vaatii toimiakseen Python 3.4 (tai uudempi). Lisäksi tarvitaan
seuraavat ulkoiset kirjastot:

requests           HTTP kirjasto
pytz               Kalenteri kirjasto

(asennus: pip3 install kirjastonnimi)

Huom. Jos työkalun haluaa toimiva myös muilla kuin omalla käyttäjällä, kannattaa kirjastot asentaa pääkäyttäjänä unix:ssa.

Tiedostot/hakemistot
====================
certs/             *.pem tiedostot
libs/              fconfig.py ja muiden tarpeellisten tiedostojen säilytyspaikka
xml/               xml requestit
log/               soapreq logit
peeks/             putsi peek vastaukset

fconfig.py         Ohjelman muokattavat parametrit

kulugen.py         Kulutusgeneraattori
kpgen.py           Käyttöpaikkageneraattori
sopimusgen.py      Sopimusgeneraattori
soapreq.py         Soap request lähetin
datareq.py         Käyttöpaikan kulutustietojen lähetin
putsi.py           Datahub response jonon tyhjennin

clean.sh           Siivous scripti (unix)
clean.bat          Siivous scripti (windows)

kpgen (Käyttöpaikkageneraattori)
================================
Käyttöpaikkageneraattorilla luodaan haluttu määrä halutunlaisilla
parametreillä varustettuja käyttöpaikkoja. Generaattoria käytetään
joko suoraan ilman komentoriviparametreja jolloin ohjelma kyselee
kaiken tarpeellisen ja lopuksi luo halutun määrän käyttöpaikkoja
kp.csv tiedostoon joka sijaitsee samassa hakemistossa. xml hakemistoon
luodaan myös datahubille lähetettävät soap xml tiedostot.

Ohjelma tunnistaa seuraavat komentoriviparametrit:

-j DSO id
-m MGA id
-l käyttöpaikkojen lukumäärä
-t käyttöpaikan tyyppi (AG01/AG02)
-r etäluvun tila (0/1)
-M mittaustapa (E13/E14/E16)
-h lyhyet käyttöohjeet

Käyttäessä komentoriviparametrejä, kaikki käytössä olevat parametrit
tulee asettaa. Puuttuvista parametreistä tulee virheilmoitus.

Komentorivillä annettujen parametrien oikeellisuutta ei tarkisteta
erikseen joten syötetyt arvot on käyttäjän vastuulla.

sopimusgen (Sopimusgeneraattori)
================================
Sopimusgeneraattorilla luodaan aikaisemmin luoduille käyttöpaikoille
sopimukset jotka muodostetaan xml hakemistoon soap xml tiedostoiksi.

Ohjelma ei ota mitään komentoriviparametrejä.

Käyttö edellyttää kp.csv tiedostoa joka luodaan kpgen:llä.

kulugen (Kulutusgeneraattori)
=============================
Kulutusgeneraattorilla luodaan aikaisemmin luoduille käyttöpaikoille
halutulle ajalle kulutusta. Oletuksena kulutustiedot luodaan kaikille
käyttöpaikoille sekä rajapisteille.

Ilman parametrejä ohjelma kysyy käyttäjältä tarvittavat tiedot ja luo
käyttöpaikat.

Ohjelma tunnistaa seuraavat komentoriviparametrit:

-s aloituspäivä muodossa dd.mm.yyyy 
-d vuorokausien lukumäärä
-h lyhyet käyttöohjeet

Muodostetut käyttötiedot tallennetaan xml kansioon.

soapreq (Soap Requester)
========================
Soap Requesterilla lähetetään aikaisemmin luodut käyttöpaikat ja
sopimukset datahubille. Onnistuneet lähetykset nimetään xml kansiossa
uudelleen DONE_ alkuisiksi. Jos lähetys osalla tai kaikkien kanssa
epäonnistuu, lähetyksen voi tehdä uudelleen kunnes kaikki xml:t on
merkitty lähetetyksi.

Kaikista lähetyksistä vastauksena saatu viesti tallennetaan log hakemistoon.

Ohjelma ei ota mitään komentoriviparametrejä.

datareq (Data Requester)
========================
Data Requester lähettää aikaisemmin kulutusgeneraattorilla luodut
xml:t datahubille. Onnistuneet lähetykset nimetään uudelleen xml
kansiossa DONE_ alkuisiksi. Jos lähetys osalla tai kaikkien kanssa
epäonnistuu, lähetyksen voi tehdä uudelleen kunnes kaikki xml:t on
merkitty lähetetyksi.

putsi (Peek & Dequeue)
======================
Peek & Dequeue hakee datahubilta halutun käyttäjän statusviestien
jonosta kaikki siellä olevat viestit ja kuittaa ne luetuksi. Saadut
viestit tallennetaan peeks hakemistoon.

fconfig (Sähkömarkkinasimulaattorin asetustiedosto)
===================================================
Tiedosto sisältää kaikki kpgenin ja lähetysohjelmien vaatimat
parametrit jotka tulee asettaa ennen ohjelmien käyttöönottoa.

fconfig tiedosto sisältää lyhyet ohjeet jokaiselle parametrille.

Käyttöohjeet
============
Ennen käyttöönottoa on ympäristöön asennettava vaadittavat ulkoiset
kirjastot ja varmistettava että käytössä on riittävän tuore python3.

Ohjelmia ajetaan komentoriviltä (python3 ohjelma.py).
Mahdollisten komentoriviparametrien järjestyksellä ei ole merkitystä.

Unix ympäristössä, aja "chmod 755 *.py *.sh" jonka jälkeen ohjelmat voi
ajaa "./ohjelma.py"

Normaali sähkömarkkinoiden luominen toteutetaan järjestyksessä:

1. kpgen (luodaan käyttöpaikat)
2. sopimusgen (luodaan sopimukset käyttöpaikoille)
3. soapreq (lähetetään käyttöpaikka ja sopimus requestit serverille)
4. kulugen (luodaan kulutusdataa käyttöpaikoille ja rajapisteille)
5. datareq (lähetetään käyttöpaikkojen ja rajapisteiden kulutustieto
   requestit serverille)

Myös pelkkien käyttöpaikkojen luominen onnistuu, silloin ajetaan vain
kpgen ennen lähettämistä (soapreq).

Datahubille lähettäminen edellyttää sertifikaattia joka on toimitettu
kaikille osapuolille. certs/ hakemistossa lyhyet ohjeet (pura_pfx.txt)
joilla toimitettu .pfx saadaan purettua käyttöön.

Ohjelmien omatoiminen puukottaminen omalla vastuulla.

-------------------------------------------
Tekijä: Tommi Raulahti / Prove Expertise Oy
Asiakas: Fingrid Datahub Oy
-------------------------------------------
