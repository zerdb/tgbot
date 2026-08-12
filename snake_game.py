import pygame
import random
import sys

# Инициализация Pygame
pygame.init()

# Константы
WIDTH = 600
HEIGHT = 400
CELL_SIZE = 20
FPS = 10

# Цвета
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
DARK_GREEN = (0, 200, 0)

# Направления
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)


class Snake:
    def __init__(self):
        self.reset()

    def reset(self):
        start_x = WIDTH // (2 * CELL_SIZE)
        start_y = HEIGHT // (2 * CELL_SIZE)
        self.body = [(start_x, start_y), (start_x - 1, start_y), (start_x - 2, start_y)]
        self.direction = RIGHT
        self.grow = False

    def move(self):
        head_x, head_y = self.body[0]
        dir_x, dir_y = self.direction
        new_head = (head_x + dir_x, head_y + dir_y)

        self.body.insert(0, new_head)
        if not self.grow:
            self.body.pop()
        else:
            self.grow = False

    def change_direction(self, new_direction):
        # Запрещаем разворот на 180 градусов
        if (new_direction[0] * -1, new_direction[1] * -1) != self.direction:
            self.direction = new_direction

    def check_collision(self):
        head = self.body[0]
        
        # Проверка столкновения со стенами
        if head[0] < 0 or head[0] >= WIDTH // CELL_SIZE or head[1] < 0 or head[1] >= HEIGHT // CELL_SIZE:
            return True
        
        # Проверка столкновения с самим собой
        if head in self.body[1:]:
            return True
        
        return False

    def draw(self, screen):
        for i, segment in enumerate(self.body):
            x = segment[0] * CELL_SIZE
            y = segment[1] * CELL_SIZE
            color = DARK_GREEN if i == 0 else GREEN
            pygame.draw.rect(screen, color, (x, y, CELL_SIZE - 1, CELL_SIZE - 1))


class Food:
    def __init__(self, snake_body):
        self.position = self.spawn(snake_body)

    def spawn(self, snake_body):
        while True:
            x = random.randint(0, WIDTH // CELL_SIZE - 1)
            y = random.randint(0, HEIGHT // CELL_SIZE - 1)
            if (x, y) not in snake_body:
                return (x, y)

    def draw(self, screen):
        x = self.position[0] * CELL_SIZE
        y = self.position[1] * CELL_SIZE
        pygame.draw.rect(screen, RED, (x, y, CELL_SIZE - 1, CELL_SIZE - 1))


class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('Змейка')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.snake = Snake()
        self.food = Food(self.snake.body)
        self.score = 0
        self.game_over = False

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            if event.type == pygame.KEYDOWN:
                if self.game_over:
                    if event.key == pygame.K_SPACE:
                        self.restart()
                    elif event.key == pygame.K_ESCAPE:
                        return False
                else:
                    if event.key == pygame.K_UP or event.key == pygame.K_w:
                        self.snake.change_direction(UP)
                    elif event.key == pygame.K_DOWN or event.key == pygame.K_s:
                        self.snake.change_direction(DOWN)
                    elif event.key == pygame.K_LEFT or event.key == pygame.K_a:
                        self.snake.change_direction(LEFT)
                    elif event.key == pygame.K_RIGHT or event.key == pygame.K_d:
                        self.snake.change_direction(RIGHT)
                    elif event.key == pygame.K_ESCAPE:
                        return False
        
        return True

    def update(self):
        if self.game_over:
            return

        self.snake.move()

        # Проверка столкновений
        if self.snake.check_collision():
            self.game_over = True
            return

        # Проверка поедания еды
        if self.snake.body[0] == self.food.position:
            self.snake.grow = True
            self.score += 10
            self.food = Food(self.snake.body)

    def draw(self):
        self.screen.fill(BLACK)
        
        self.snake.draw(self.screen)
        self.food.draw(self.screen)

        # Отображение счета
        score_text = self.font.render(f'Счет: {self.score}', True, WHITE)
        self.screen.blit(score_text, (10, 10))

        if self.game_over:
            game_over_text = self.font.render('ИГРА ОКОНЧЕНА!', True, RED)
            restart_text = self.font.render('Нажмите SPACE для рестарта', True, WHITE)
            escape_text = self.font.render('ESC для выхода', True, WHITE)
            
            text_rect = game_over_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 30))
            restart_rect = restart_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 10))
            escape_rect = escape_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 50))
            
            self.screen.blit(game_over_text, text_rect)
            self.screen.blit(restart_text, restart_rect)
            self.screen.blit(escape_text, escape_rect)

        pygame.display.flip()

    def restart(self):
        self.snake.reset()
        self.food = Food(self.snake.body)
        self.score = 0
        self.game_over = False

    def run(self):
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()


if __name__ == '__main__':
    game = Game()
    game.run()
