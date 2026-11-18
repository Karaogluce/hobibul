# Pinterest taslakları ve panolar

Bu dosya Pinterest için **elle yayınlanacak** taslakları tanımlar. Depoda duran
görseller ve metinler yalnızca taslaktır; hiçbir sosyal ağa otomatik gönderim
yapılmaz, Pinterest API'si kullanılmaz. Yayınlama, panoların açılması ve hesap
ayarları site sahibinin işidir.

Kurallar:

- Her pin tek bir makaleye gider; uydurma ürün, fiyat veya fayda iddiası yok.
- Görseller depodaki makale fotoğraflarından üretilir; yapay zekâ ile üretilmiş
  stok görsel kullanılmaz.
- Başlık ve açıklamalar okuyucunun kendi kelimeleriyle yazılır; anahtar kelime
  başta durur, doldurmak için tekrarlanmaz.
- Trafik, gelir veya takipçi sayısı vaadi yoktur. Sonuç ancak Pinterest ve
  Search Console verisi geldikten sonra konuşulur.

## Pin biçimi

- Boyut: **1000 × 1500 px (2:3)**, JPEG.
- Şablon: üstte makale fotoğrafı, altta gece lacivert zemin; turuncu kategori
  etiketi, mavi ince vurgu, Georgia Bold başlık, Segoe UI Semibold etiketler.
- Renkler: `#0F0F1A` zemin, `#FE8500` vurgu, `#105BFF` ikinci vurgu,
  `#F6F7FB` metin.
- Yeniden üretmek için: `python pin_uret.py` (tek pin: `--only <ad>`).

Üretilen dosyalar `static/img/pin/` altındadır; site derlemesinde
`/img/pin/...` adresinden yayınlanır.

## Panolar (12 öneri)

| # | Pano adı | Kime | Hangi ihtiyaç | İlk bağlantı |
|---|----------|------|----------------|--------------|
| 1 | Yeni Başlayanlar İçin Hobi Fikirleri | Hobiye başlamak isteyen yetişkinler | Nereden başlayacağını bilmek | `/rehberler/` |
| 2 | Çocuklarla Evde Oynanacak Kutu Oyunları | Ebeveynler | Yaşa uygun, Türkiye'de satılan oyun | `/makale/aile-kutu-oyunlari/` |
| 3 | Punch Nakışı Fikirleri ve Başlangıç | El sanatlarına yeni başlayanlar | İlk projeyi küçük bir setle bitirmek | `/makale/punch-nakisi-nasil-yapilir-baslangic-seti/` |
| 4 | Evde Bonsai Bakımı | Bitki meraklıları | Ağacı yaşatacak doğru ekipman | `/makale/bonsai-icin-yeni-baslayanlar-rehberi-ilk-alinacak-ekipmanlar/` |
| 5 | Evde Filtre Kahve Demleme | Kahveye yeni başlayanlar | Aynı fincanı her gün tutturma | `/makale/evde-filtre-kahve-baslangic-seti-ogutucu-v60-ve-tarti/` |
| 6 | LEGO ve Model Koleksiyoncuları | Yetişkin LEGO meraklıları | Bütçeye uygun ilk seti seçmek | `/makale/lego-model-icin-yeni-baslayanlar-rehberi-ilk-alinacak-ekipmanlar/` |
| 7 | Küçük Evde Hobi Köşesi | Dar alanda yaşayanlar | Yer açmadan düzen kurmak | `/makale/hobi-odasi-nasil-kurulur/` |
| 8 | Evcil Hayvanla Hobi ve Bakım | Kedi sahipleri | Doğru tırmalama ve oyuncak seçimi | `/makale/kedi-bakim-seti-tirmalama-firca-ve-oyuncak/` |
| 9 | Hafta Sonu Deri Projeleri | El işi sevenler | Küçük bir setle ilk projeyi yapmak | `/makale/deri-isciligi-baslangic-seti-ilk-alinacaklar-2026/` |
| 10 | Evde Pizza Gecesi | Mutfakta denemek isteyenler | Ev fırınında dengeli pişirme | `/makale/evde-pizza-firini-g3-ferrari-delizia-ile-baslangic/` |
| 11 | Yoga ve Evde Fitness Başlangıcı | Evde spora başlayanlar | Mat ve temel ekipman seçimi | `/makale/yoga-mati-secimi-yeni-baslayanlar-icin/` |
| 12 | Hobi Hediyesi Fikirleri | Hediye arayanlar | Kime ne alınacağını bilmek | `/makale/yilbasi-hediyesi-kutu-oyunlari/` |

Pano adları ihtiyaç diline göre yazıldı; "kutu oyun" gibi geniş bir başlık
yerine "çocuklarla evde oynanacak kutu oyunları" gibi arama niyetini taşıyan
adlar kullanıldı. Gerekirse pano adları kendi kitlenize göre daraltılabilir.

## Pin taslakları (5)

Bağlantılar mutlak adrestir; panoya eklerken aynen kullanılabilir.

### 1. Aile kutu oyunları

- Dosya: `static/img/pin/aile-kutu-oyunlari.jpg`
- Başlık: `Çocuklarla Evde Oynanacak Kutu Oyunları: Türkiye'de Satılanlar`
- Açıklama: `Çocuklarla evde oynanacak kutu oyunları arıyorsan önce yaş aralığına ve oyuncu sayısına bak. Türkiye'de satılan aile oyunlarını ve seçim kriterlerini rehberde topladık: https://hobibul.com.tr/makale/aile-kutu-oyunlari/`
- Pano: Çocuklarla Evde Oynanacak Kutu Oyunları
- Not: Makalenin kendi fotoğrafı yok; görsel aynı kategorideki yılbaşı kutu
  oyunu fotoğrafından (`yilbasi-hediyesi-kutu-oyunlari.webp`) üretildi.

### 2. Punch nakışı

- Dosya: `static/img/pin/punch-nakisi-baslangic-seti.jpg`
- Başlık: `Punch Nakışı Nasıl Yapılır? Başlangıç Seti ve İlk Proje`
- Açıklama: `Punch nakışına başlamak için iğne, kasnak ve ip seçimini adım adım anlatıyoruz. İlk projede sık yapılan hataları ve set seçerken bakılacak ölçüleri rehberde bul: https://hobibul.com.tr/makale/punch-nakisi-nasil-yapilir-baslangic-seti/`
- Pano: Punch Nakışı Fikirleri ve Başlangıç

### 3. Bonsai

- Dosya: `static/img/pin/bonsai-yeni-baslayan.jpg`
- Başlık: `Bonsai İçin İlk Alınacak Ekipmanlar: Yeni Başlayan Rehberi`
- Açıklama: `Bonsai ağacı bakımına başlarken ilk alınacak ekipmanları sıraladık: makas, tel ve toprak. Gereksiz harcamadan kaçınmak için listeye bak: https://hobibul.com.tr/makale/bonsai-icin-yeni-baslayanlar-rehberi-ilk-alinacak-ekipmanlar/`
- Pano: Evde Bonsai Bakımı

### 4. Filtre kahve

- Dosya: `static/img/pin/filtre-kahve-baslangic-seti.jpg`
- Başlık: `Evde Filtre Kahve Başlangıç Seti: Öğütücü, V60 ve Tartı`
- Açıklama: `Filtre kahve başlangıç seti kurarken öğütücü, V60 ve tartı seçimini karşılaştırdık. Aynı fincanı her gün tutturmanın yolu rehberde: https://hobibul.com.tr/makale/evde-filtre-kahve-baslangic-seti-ogutucu-v60-ve-tarti/`
- Pano: Evde Filtre Kahve Demleme

### 5. LEGO

- Dosya: `static/img/pin/lego-yeni-baslayan.jpg`
- Başlık: `LEGO'ya Yeni Başlayanlar: İlk Set Nasıl Seçilir?`
- Açıklama: `LEGO ve model hobisine başlarken ilk set seçimi bütçeni belirler. Parça sayısı, tema ve yaş aralığına göre seçim ipuçları rehberde: https://hobibul.com.tr/makale/lego-model-icin-yeni-baslayanlar-rehberi-ilk-alinacak-ekipmanlar/`
- Pano: LEGO ve Model Koleksiyoncuları

## İş akışı

1. Taslakları bu depoda gözden geçir (pull request).
2. Onayladığın pinleri Pinterest'e **elle** yükle; panoyu ve açıklamayı yukarıdaki
   kayıttan kopyala.
3. İlk 2–4 hafta yalnızca kendi panolarına düzenli ekleme yap; toplu/otomatik
   gönderim kullanma.
4. Hangi pinin tıklama getirdiğini Pinterest analitiğinden izle; veri gelmeden
   başarı iddiası yazma. Yeni pin fikirleri bu dosyaya eklenir, eski kayıtlar
   silinmez.
