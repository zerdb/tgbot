import random
import tkinter as tk
from tkinter import messagebox

COLS = 10
ROWS = 20
CELL = 30
SIDE = 190
WIDTH = COLS * CELL
HEIGHT = ROWS * CELL

SHAPES = {
    "I": [[(0,1),(1,1),(2,1),(3,1)], [(2,0),(2,1),(2,2),(2,3)]],
    "O": [[(1,0),(2,0),(1,1),(2,1)]],
    "T": [[(1,0),(0,1),(1,1),(2,1)], [(1,0),(1,1),(2,1),(1,2)], [(0,1),(1,1),(2,1),(1,2)], [(1,0),(0,1),(1,1),(1,2)]],
    "S": [[(1,0),(2,0),(0,1),(1,1)], [(1,0),(1,1),(2,1),(2,2)]],
    "Z": [[(0,0),(1,0),(1,1),(2,1)], [(2,0),(1,1),(2,1),(1,2)]],
    "J": [[(0,0),(0,1),(1,1),(2,1)], [(1,0),(2,0),(1,1),(1,2)], [(0,1),(1,1),(2,1),(2,2)], [(1,0),(1,1),(0,2),(1,2)]],
    "L": [[(2,0),(0,1),(1,1),(2,1)], [(1,0),(1,1),(1,2),(2,2)], [(0,1),(1,1),(2,1),(0,2)], [(0,0),(1,0),(1,1),(1,2)]],
}

COLORS = {
    "I": "#37c9ff", "O": "#ffd83d", "T": "#b76cff", "S": "#55d86a",
    "Z": "#ff5b68", "J": "#4f7dff", "L": "#ff9b42"
}

class Tetris(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tkinter Tetris")
        self.resizable(False, False)
        self.configure(bg="#ffffff")
        self.canvas = tk.Canvas(self, width=WIDTH + SIDE, height=HEIGHT, bg="#f3f4f6", highlightthickness=0)
        self.canvas.pack()
        self.bind_all("<Key>", self.on_key)
        self.after_id = None
        self.best = 0
        self.new_game()

    def new_game(self):
        if self.after_id:
            self.after_cancel(self.after_id)
        self.board = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.score = 0
        self.lines = 0
        self.level = 1
        self.paused = False
        self.game_over = False
        self.bag = []
        self.next_kind = self.take_piece()
        self.spawn()
        self.draw()
        self.schedule()

    def take_piece(self):
        if not self.bag:
            self.bag = list(SHAPES)
            random.shuffle(self.bag)
        return self.bag.pop()

    def spawn(self):
        self.kind = self.next_kind
        self.next_kind = self.take_piece()
        self.rotation = 0
        self.x = 3
        self.y = -1
        if not self.valid(self.x, self.y, self.rotation):
            self.game_over = True
            self.best = max(self.best, self.score)

    def cells(self, x=None, y=None, rotation=None):
        x = self.x if x is None else x
        y = self.y if y is None else y
        rotation = self.rotation if rotation is None else rotation
        return [(x + dx, y + dy) for dx, dy in SHAPES[self.kind][rotation]]

    def valid(self, x, y, rotation):
        for cx, cy in self.cells(x, y, rotation):
            if cx < 0 or cx >= COLS or cy >= ROWS:
                return False
            if cy >= 0 and self.board[cy][cx]:
                return False
        return True

    def move(self, dx, dy):
        if self.valid(self.x + dx, self.y + dy, self.rotation):
            self.x += dx
            self.y += dy
            return True
        return False

    def rotate(self):
        new_rotation = (self.rotation + 1) % len(SHAPES[self.kind])
        for kick in (0, -1, 1, -2, 2):
            if self.valid(self.x + kick, self.y, new_rotation):
                self.x += kick
                self.rotation = new_rotation
                return

    def drop(self):
        distance = 0
        while self.move(0, 1):
            distance += 1
        self.score += distance * 2
        self.lock()

    def ghost_y(self):
        gy = self.y
        while self.valid(self.x, gy + 1, self.rotation):
            gy += 1
        return gy

    def lock(self):
        for x, y in self.cells():
            if y < 0:
                self.game_over = True
                self.best = max(self.best, self.score)
                self.draw()
                return
            self.board[y][x] = self.kind
        self.clear_lines()
        self.spawn()
        self.draw()

    def clear_lines(self):
        full = [r for r in self.board if all(r)]
        count = len(full)
        if count:
            self.board = [[None] * COLS for _ in range(count)] + [r for r in self.board if not all(r)]
            points = [0, 100, 300, 500, 800][count]
            self.score += points * self.level
            self.lines += count
            self.level = self.lines // 10 + 1
            self.best = max(self.best, self.score)

    def tick(self):
        self.after_id = None
        if not self.paused and not self.game_over:
            if not self.move(0, 1):
                self.lock()
            self.draw()
        self.schedule()

    def schedule(self):
        if not self.game_over:
            speed = max(80, 700 - (self.level - 1) * 55)
            self.after_id = self.after(speed, self.tick)

    def on_key(self, event):
        key = event.keysym.lower()
        if key == "r":
            self.new_game()
            return
        if key in ("p", "escape") and not self.game_over:
            self.paused = not self.paused
            self.draw()
            return
        if self.paused or self.game_over:
            return
        if key in ("left", "a"):
            self.move(-1, 0)
        elif key in ("right", "d"):
            self.move(1, 0)
        elif key in ("down", "s"):
            if self.move(0, 1):
                self.score += 1
            else:
                self.lock()
        elif key in ("up", "w", "x"):
            self.rotate()
        elif key == "space":
            self.drop()
        self.draw()

    def block(self, x, y, color, outline="#cbd5e1"):
        px, py = x * CELL, y * CELL
        self.canvas.create_rectangle(px + 2, py + 2, px + CELL - 2, py + CELL - 2, fill=color, outline=outline, width=2)
        self.canvas.create_line(px + 5, py + 5, px + CELL - 6, py + 5, fill="#ffffff", stipple="gray50")

    def draw(self):
        self.canvas.delete("all")
        for y in range(ROWS):
            for x in range(COLS):
                x1, y1 = x * CELL, y * CELL
                self.canvas.create_rectangle(x1, y1, x1 + CELL, y1 + CELL, outline="#d1d5db")
                if self.board[y][x]:
                    self.block(x, y, COLORS[self.board[y][x]])

        if not self.game_over:
            gy = self.ghost_y()
            for x, y in self.cells(self.x, gy, self.rotation):
                if y >= 0:
                    px, py = x * CELL, y * CELL
                    self.canvas.create_rectangle(px + 5, py + 5, px + CELL - 5, py + CELL - 5, outline="#9ca3af", width=2)
            for x, y in self.cells():
                if y >= 0:
                    self.block(x, y, COLORS[self.kind])

        sx = WIDTH + 22
        self.canvas.create_text(sx, 28, text="TETRIS", anchor="nw", fill="#111827", font=("TkDefaultFont", 22, "bold"))
        self.canvas.create_text(sx, 86, text=f"Счёт\n{self.score}", anchor="nw", fill="#374151", font=("TkDefaultFont", 12, "bold"))
        self.canvas.create_text(sx, 145, text=f"Линии  {self.lines}\nУровень {self.level}\nРекорд  {self.best}", anchor="nw", fill="#6b7280", font=("TkDefaultFont", 11))
        self.canvas.create_text(sx, 225, text="Следующая", anchor="nw", fill="#374151", font=("TkDefaultFont", 11, "bold"))

        shape = SHAPES[self.next_kind][0]
        for dx, dy in shape:
            px = sx + dx * 22
            py = 258 + dy * 22
            self.canvas.create_rectangle(px, py, px + 19, py + 19, fill=COLORS[self.next_kind], outline="#cbd5e1")

        self.canvas.create_text(sx, 355, text="Управление", anchor="nw", fill="#374151", font=("TkDefaultFont", 11, "bold"))
        controls = "← → / A D   движение\n↓ / S       вниз\n↑ / W / X   поворот\nSpace       сброс\nP / Esc     пауза\nR           заново"
        self.canvas.create_text(sx, 382, text=controls, anchor="nw", fill="#6b7280", font=("TkFixedFont", 9))

        if self.paused or self.game_over:
            self.canvas.create_rectangle(28, 230, WIDTH - 28, 370, fill="#ffffff", outline="#cbd5e1", width=2)
            title = "ПАУЗА" if self.paused else "ИГРА ОКОНЧЕНА"
            hint = "P / Esc — продолжить" if self.paused else "R — новая игра"
            self.canvas.create_text(WIDTH / 2, 275, text=title, fill="#111827", font=("TkDefaultFont", 18, "bold"))
            self.canvas.create_text(WIDTH / 2, 320, text=hint, fill="#6b7280", font=("TkDefaultFont", 11))

if __name__ == "__main__":
    Tetris().mainloop()
