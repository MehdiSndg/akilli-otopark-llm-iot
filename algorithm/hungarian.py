"""
hungarian.py — Hungarian (Kuhn-Munkres) algoritması: optimal atama (saf Python).

Bir maliyet matrisinde (satır = araç, sütun = park yeri) toplam maliyeti en küçük
yapan birebir atamayı O(n^3) zamanda bulur. Greedy (açgözlü) atamadan farkı:
iki aracı asla aynı yere göndermez ve TOPLAM mesafeyi optimize eder; bir aracı
biraz uzağa yollamak diğerini çok daha iyi bir yere koyacaksa onu seçer.

Kullanılan yöntem: potansiyel (u, v) tabanlı, artırıcı yol (augmenting path)
kuran klasik O(n^3) varyant. Dikdörtgen matrisleri (araç sayısı <= yer sayısı)
doğrudan destekler.
"""

INF = float("inf")


def hungarian(cost):
    """En küçük maliyetli birebir atamayı bul.

    cost : rows x cols maliyet matrisi (liste-listesi). rows <= cols OLMALI.
    Döner: uzunluğu rows olan liste; assign[i] = i. araca atanan sütun (yer)
           indeksi. (rows <= cols olduğundan her satır bir sütuna atanır.)
    """
    n = len(cost)
    if n == 0:
        return []
    m = len(cost[0])
    if n > m:
        raise ValueError("hungarian: satır (araç) sayısı sütun (yer) sayısını aşamaz")

    # 1-indeksli potansiyeller ve eşleşme dizileri (e-maxx tarzı uyarlama)
    u = [0.0] * (n + 1)          # satır potansiyelleri
    v = [0.0] * (m + 1)          # sütun potansiyelleri
    p = [0] * (m + 1)            # p[j] = j. sütuna atanmış satır (0 = boş)
    way = [0] * (m + 1)          # artırıcı yol yeniden kurulumu için

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0                    # "sanal" başlangıç sütunu
        minv = [INF] * (m + 1)
        used = [False] * (m + 1)
        # i. satır için artırıcı yol bulunana dek genişlet
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = -1
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            # potansiyelleri güncelle
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:        # boş sütuna ulaştık -> yol tamam
                break
        # artırıcı yol boyunca eşleşmeleri kaydır
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1

    assign = [-1] * n
    for j in range(1, m + 1):
        if p[j] != 0:
            assign[p[j] - 1] = j - 1
    return assign
