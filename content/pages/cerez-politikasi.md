---
title: "Çerez Politikası"
path: "/cerez-politikasi/"
nav: "Çerez Politikası"
order: 50
meta_title: "Çerez Politikası | Hobi Bul"
meta_description: "Hobi Bul çerez politikası: Consent Mode v2, GA4 çerezleri, localStorage tercihi ve ileride AdSense üçüncü taraf çerezleri."
updated: "2026-10-29"
---

Çerez, sitenin tarayıcına bıraktığı küçük metin dosyasıdır. Hobi Bul’un kendi yazdığı bir çerez yok. Tercih kaydı çerez değil; tarayıcının localStorage alanındadır. Genel çerçeve [gizlilik politikasında](/gizlilik-politikasi/), başvuru yolu [KVKK metninde](/kvkk/).

## Açılışta her şey kapalı

Google Analytics 4 betiği her sayfada yüklenir. Ondan önce Google Consent Mode v2 varsayılanı yazılır. analytics_storage, ad_storage, ad_user_data ve ad_personalization denied, yani kapalıdır. Kabul et dersen dördü granted olur. Reddet dersen dördü denied kalır ve bu seçim hatırlanır. Ayarlar’dan ölçüm ile reklamı ayrı ayrı açıp kapatabilirsin.

## Ne saklanır

| Kayıt | Kim | Ne işe yarar | Ne zaman |
| --- | --- | --- | --- |
| hobibul_consent_v1 | Hobi Bul, localStorage | Analitik ve reklam izninin açık mı kapalı mı olduğu | Sen silene veya site verisini temizleyene kadar. Sunucuya gitmez. |
| _ga | Google Analytics | Tarayıcıları birbirinden ayırmak | Yalnızca analitik izni açıkken. Google’ın süresi yaklaşık 2 yıldır. |
| _ga_ ve ölçüm kimliği | Google Analytics | Oturum durumunu tutmak | Yalnızca analitik izni açıkken. Süre yaklaşık 2 yıldır. |

Zorunlu bir çerez kullanmıyoruz. Sayfalar statik; siteyi açmak için çerez şart değil.

Analitik izni açıkken sayfa görüntülemesi ve ortaklık tıklaması ayrıca Supabase’e gider. Bu bir çerez değil, bir istek. İzin kapalıyken bu istek de atılmaz. Ayrıntı gizlilik politikasında.

## Reklam çerezleri ve AdSense

Şu an sitede reklam çerezi yok. Google AdSense ileride eklenirse Google ve reklam ortakları, reklam gösterimi, dönüşüm ölçümü ve kişiselleştirme için üçüncü taraf çerezleri yazabilir. Bu, reklam izinlerini açmana bağlıdır. Üç sinyal bir arada durur: ad_storage, ad_user_data, ad_personalization. Üçü de varsayılan olarak kapalıdır. Ayarlar’da “Reklam ölçümü ve kişiselleştirme” kutusunu açmadan bu depolama granted olmaz.

Kişiselleştirilmiş reklamdan çıkmak için Google’ın kendi sayfası: [https://adssettings.google.com/](https://adssettings.google.com/). Tarayıcıya Google’ın Analytics devre dışı bırakma eklentisini de kurabilirsin: [https://tools.google.com/dlpage/gaoptout](https://tools.google.com/dlpage/gaoptout). Eklenti, sitedeki bantın yerine geçmez; ikisi ayrı katmandır.

## Ortaklık sitelerinin çerezleri

Amazon Associates, Admitad ve Gelir Ortakları (Trendyol, Hepsiburada) bağlantısına tıkladığında çerez o sitenin alanında kurulur. Kontrol bizde değil. Hangi düğmenin ortaklık linki olduğu [affiliate açıklamasında](/affiliate-aciklamasi/).

## Tercihi nasıl değiştirirsin

Bantta üç düğme var: Kabul et, Reddet, Ayarlar. Seçim bu tarayıcıda kalır. Her sayfanın footer’ındaki “Çerez tercihlerini değiştir” düğmesi bandı yeniden açar. Çerezleri tarayıcı ayarından da silebilirsin. localStorage ayrı bir bölümdedir; tarayıcıda site verisi veya yerel depolama diye geçer. Onu silersen bant bir sonraki ziyarette yine çıkar.
