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
        bg = (52, 56, 70) if self.enabled else (44, 46, 56)
        border = config.COLOR_SUGGESTED if (self.active and self.enabled) else (90, 95, 110)
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
        color = (80, 130, 200) if self.enabled else (70, 73, 85)
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        label = self.font.render(self.label, True, config.COLOR_TEXT)
        surface.blit(label, (self.rect.centerx - label.get_width() // 2,
                             self.rect.centery - label.get_height() // 2))


class ChatLog:
    """Kullanıcı ve sistem mesajlarını kaydırmalı gösteren sohbet alanı."""

    def __init__(self, font):
        self.font = font
        self.messages = []   # (role, text); role: "user" | "system" | "info"

    def add(self, role, text):
        self.messages.append((role, text))

    def draw(self, surface, rect):
        x, y, w, h = rect
        line_h = self.font.get_height() + 2
        role_colors = {
            "user": (130, 200, 255),
            "system": config.COLOR_TEXT,
            "info": config.COLOR_TEXT_DIM,
        }

        # Tüm satırları hazırla (en yeni en altta), sığan kadarını alttan göster
        rendered = []
        for role, text in self.messages:
            prefix = {"user": "Sürücü: ", "system": "Sistem: ", "info": ""}[role]
            for i, line in enumerate(wrap_text(prefix + text, self.font, w - 16)):
                rendered.append((line, role_colors[role]))
            rendered.append(("", role_colors[role]))  # mesajlar arası boşluk

        max_lines = h // line_h
        visible = rendered[-max_lines:]
        for i, (line, color) in enumerate(visible):
            if line:
                surface.blit(self.font.render(line, True, color),
                             (x + 8, y + i * line_h))
