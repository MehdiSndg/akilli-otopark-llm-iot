"""
widgets.py — Pygame arayüz bileşenleri.

Pygame'de hazır metin kutusu/sohbet alanı olmadığı için elle yazılır:
- InputBox : klavyeden metin girişi (imleç, backspace, Enter ile gönderme)
- Button   : tıklanabilir gönder butonu
- ChatLog  : kullanıcı/sistem mesajlarını kelime kaydırmalı (word-wrap) gösterir
"""

import pygame

import config


def wrap_text(text, font, max_width):
    """Metni verilen genişliğe sığacak satırlara böl (kelime kaydırma)."""
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        line = ""
        for word in words:
            trial = word if not line else line + " " + word
            if font.size(trial)[0] <= max_width:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = word
        lines.append(line)
    return lines


class InputBox:
    """Tek satırlık metin giriş kutusu."""

    def __init__(self, rect, font, placeholder="Mesajınızı yazın..."):
        self.rect = pygame.Rect(rect)
        self.font = font
        self.text = ""
        self.placeholder = placeholder
        self.active = True
        self.enabled = True

    def handle_event(self, event):
        """Olayı işle. Enter'a basılınca girilen metni döndürür, aksi halde None."""
        if not self.enabled:
            return None
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                text = self.text.strip()
                self.text = ""
                return text or None
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.unicode and event.unicode.isprintable():
                self.text += event.unicode
        return None

    def draw(self, surface):
        bg = (43, 47, 60) if self.enabled else (35, 38, 48)
        border = config.COLOR_ACCENT if (self.active and self.enabled) else (74, 80, 96)
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        pygame.draw.rect(surface, border, self.rect, width=2, border_radius=8)

        if self.text:
            shown, color = self.text, config.COLOR_TEXT
        else:
            shown, color = self.placeholder, config.COLOR_TEXT_DIM
        # Kutuya sığması için soldan kırp (uzun metinde sonu göster)
        while self.font.size(shown)[0] > self.rect.width - 20 and len(shown) > 1:
            shown = shown[1:]
        label = self.font.render(shown, True, color)
        surface.blit(label, (self.rect.x + 10,
                             self.rect.y + (self.rect.height - label.get_height()) // 2))

        # Yanıp sönen imleç
        if self.active and self.enabled and pygame.time.get_ticks() % 1000 < 500:
            cx = self.rect.x + 10 + self.font.size(shown)[0] + 2
            cy = self.rect.y + 8
            pygame.draw.line(surface, config.COLOR_TEXT, (cx, cy),
                             (cx, cy + self.rect.height - 16), 2)


class Button:
    """Basit tıklanabilir buton."""

    def __init__(self, rect, font, label):
        self.rect = pygame.Rect(rect)
        self.font = font
        self.label = label
        self.enabled = True

    def clicked(self, event):
        return (self.enabled and event.type == pygame.MOUSEBUTTONDOWN
                and self.rect.collidepoint(event.pos))

    def draw(self, surface):
        color = config.COLOR_ACCENT if self.enabled else (62, 66, 80)
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        label = self.font.render(self.label, True, config.COLOR_TEXT)
        surface.blit(label, (self.rect.centerx - label.get_width() // 2,
                             self.rect.centery - label.get_height() // 2))


class Segmented:
    """Yan yana seçeneklerden birini seçtiren kontrol (ör. Sol giriş / Sağ giriş).

    options: [(etiket, değer), ...]. Seçili seçenek accent ile vurgulanır.
    value özelliği seçili değeri döndürür."""

    def __init__(self, rect, font, options, selected=0):
        self.rect = pygame.Rect(rect)
        self.font = font
        self.options = options
        self.selected = selected

    @property
    def value(self):
        return self.options[self.selected][1]

    def handle_event(self, event):
        """Tıklanan segmenti seç. Seçim değiştiyse True döner."""
        if event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            n = len(self.options)
            seg_w = self.rect.width / n
            idx = int((event.pos[0] - self.rect.x) // seg_w)
            idx = max(0, min(n - 1, idx))
            if idx != self.selected:
                self.selected = idx
                return True
        return False

    def draw(self, surface):
        n = len(self.options)
        seg_w = self.rect.width / n
        pygame.draw.rect(surface, config.COLOR_CARD, self.rect, border_radius=8)
        for i, (label, _) in enumerate(self.options):
            seg = pygame.Rect(int(self.rect.x + i * seg_w), self.rect.y,
                              int(seg_w), self.rect.height)
            if i == self.selected:
                pygame.draw.rect(surface, config.COLOR_ACCENT, seg.inflate(-6, -6),
                                 border_radius=6)
                tc = config.COLOR_TEXT
            else:
                tc = config.COLOR_TEXT_DIM
            lbl = self.font.render(label, True, tc)
            surface.blit(lbl, (seg.centerx - lbl.get_width() // 2,
                               seg.centery - lbl.get_height() // 2))


class ChatLog:
    """Kullanıcı ve sistem mesajlarını kaydırmalı gösteren sohbet alanı."""

    def __init__(self, font):
        self.font = font
        self.messages = []   # (role, text); role: "user" | "system" | "info"

    def add(self, role, text):
        self.messages.append((role, text))

    def draw(self, surface, rect):
        """Mesajları balon (bubble) stilinde, en yeni en altta olacak şekilde çiz.

        Sürücü mesajı sağa hizalı accent balon; sistem cevabı sola hizalı kart
        balon; bilgi mesajı balonsuz sönük metin. Alandan taşan eski mesajlar
        kırpılır (set_clip)."""
        x, y, w, h = rect
        pad = 9
        line_h = self.font.get_height() + 3
        prev_clip = surface.get_clip()
        surface.set_clip(pygame.Rect(x, y, w, h))

        yy = y + h
        for role, text in reversed(self.messages):
            max_w = int(w * 0.82) - 2 * pad
            lines = wrap_text(text, self.font, max_w)
            tw = max((self.font.size(ln)[0] for ln in lines), default=0)
            bw = tw + 2 * pad
            bh = len(lines) * line_h + 2 * pad
            yy -= bh + 8

            if role == "user":
                bx, bubble, tc = x + w - bw - 4, config.COLOR_ACCENT_DIM, config.COLOR_TEXT
            elif role == "system":
                bx, bubble, tc = x + 4, config.COLOR_CARD, config.COLOR_TEXT
            else:  # info
                bx, bubble, tc = x + 4, None, config.COLOR_TEXT_DIM

            if bubble is not None:
                pygame.draw.rect(surface, bubble, (bx, yy, bw, bh), border_radius=12)
            for i, ln in enumerate(lines):
                surface.blit(self.font.render(ln, True, tc),
                             (bx + pad, yy + pad + i * line_h))
            if yy <= y:
                break

        surface.set_clip(prev_clip)
