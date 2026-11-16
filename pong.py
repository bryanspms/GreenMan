import pygame
import math
import random
import sys
from PIL import Image, ImageDraw, ImageFont

#Initialize pygame
pygame.init()

#Set up the display
width, height = 800, 600
screen = pygame.display.set_mode((width, height))
pygame.display.set_caption("Pong")

#Colors
white = (255, 255, 255)
black = (0, 0, 0)

#Paddle settings
paddlewidth, paddleheight = 10, 100
paddle_speed = 10

#Ball settings
ball_radius = 10
ballspeedx, ballspeedy = 3, 3

#Paddle positions
leftpaddley = (height - paddleheight) // 2
rightpaddley = (height - paddleheight) // 2

#Ball position
ball_x = width // 2
ball_y = random.randint(ball_radius, height - ball_radius)

#Clock to control the frame rate
clock = pygame.time.Clock()
score_font = ImageFont.load_default(size=48)
message_font = ImageFont.load_default(size=32)
total_balls = 11
left_score = 0
right_score = 0
game_state = "waiting"
speed_options = (0.1, 0.5, 1.0, 1.5)
speed_index = 2


def draw_text(text, font, center):
    bounds = font.getbbox(text)
    text_image = Image.new("RGBA", (bounds[2] - bounds[0], bounds[3] - bounds[1]))
    ImageDraw.Draw(text_image).text((-bounds[0], -bounds[1]), text, font=font, fill=white)
    surface = pygame.image.fromstring(text_image.tobytes(), text_image.size, "RGBA")
    screen.blit(surface, surface.get_rect(center=center))


#Game loop
tapped_keys = set()
while True:
    for event in pygame.event.get():
        if event.type == pygame.KEYDOWN:
            tapped_keys.add(event.key)
        if event.type == pygame.QUIT or (
            event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
        ):
            pygame.quit()
            sys.exit()
        if event.type == pygame.KEYDOWN and game_state in {"waiting", "finished"}:
            if event.key == pygame.K_LEFT:
                speed_index = max(0, speed_index - 1)
            elif event.key == pygame.K_RIGHT:
                speed_index = min(len(speed_options) - 1, speed_index + 1)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            if game_state == "waiting":
                game_state = "playing"
            elif game_state == "playing":
                game_state = "paused"
            elif game_state == "paused":
                game_state = "playing"
            elif game_state == "finished":
                left_score = 0
                right_score = 0
                leftpaddley = (height - paddleheight) // 2
                rightpaddley = (height - paddleheight) // 2
                ball_x = width // 2
                ball_y = random.randint(ball_radius, height - ball_radius)
                ballspeedx, ballspeedy = 3, 3
                game_state = "playing"

    if game_state == "playing":
        speed = speed_options[speed_index]
        keys = pygame.key.get_pressed()
        # Injected key taps can be pressed and released within one frame.
        keys = {key: keys[key] or key in tapped_keys for key in (pygame.K_w, pygame.K_s, pygame.K_i, pygame.K_k)}
        if keys[pygame.K_w]:
            leftpaddley = max(0, leftpaddley - paddle_speed * speed)
        if keys[pygame.K_s]:
            leftpaddley = min(height - paddleheight, leftpaddley + paddle_speed * speed)
        if keys[pygame.K_i]:
            rightpaddley = max(0, rightpaddley - paddle_speed * speed)
        if keys[pygame.K_k]:
            rightpaddley = min(height - paddleheight, rightpaddley + paddle_speed * speed)

        ball_x += ballspeedx * speed
        ball_y += ballspeedy * speed

        if ball_y <= ball_radius or ball_y >= height - ball_radius:
            ball_y = max(ball_radius, min(height - ball_radius, ball_y))
            ballspeedy = -ballspeedy

        if (
            ballspeedx < 0
            and ball_x >= 0
            and ball_x - ball_radius <= paddlewidth
            and ball_y + ball_radius >= leftpaddley
            and ball_y - ball_radius <= leftpaddley + paddleheight
        ) or (
            ballspeedx > 0
            and ball_x <= width
            and ball_x + ball_radius >= width - paddlewidth
            and ball_y + ball_radius >= rightpaddley
            and ball_y - ball_radius <= rightpaddley + paddleheight
        ):
            ballspeedx = -ballspeedx

        if ball_x + ball_radius < 0 or ball_x - ball_radius > width:
            if ball_x < 0:
                right_score += 1
            else:
                left_score += 1
            ball_x = width // 2
            ballspeedx = -ballspeedx
            if left_score + right_score == total_balls:
                game_state = "finished"
            else:
                ball_y = random.randint(ball_radius, height - ball_radius)

    # Draw everything
    screen.fill(black)
    pygame.draw.rect(screen, white, (0, round(leftpaddley), paddlewidth, paddleheight))
    pygame.draw.rect(screen, white, (width - paddlewidth, round(rightpaddley), paddlewidth, paddleheight))
    if game_state in {"playing", "paused"}:
        direction_length = math.hypot(ballspeedx, ballspeedy)
        direction_x = ballspeedx / direction_length
        direction_y = ballspeedy / direction_length
        pygame.draw.line(
            screen, (145, 145, 145),
            (round(ball_x - direction_x * ball_radius),
             round(ball_y - direction_y * ball_radius)),
            (round(ball_x - direction_x * (ball_radius + 18)),
             round(ball_y - direction_y * (ball_radius + 18))),
            3,
        )
    pygame.draw.circle(screen, white, (round(ball_x), round(ball_y)), ball_radius)
    draw_text(f"{left_score} : {right_score}", score_font, (width // 2, 35))
    draw_text(
        f"Balls remaining: {total_balls - left_score - right_score}",
        message_font, (width // 2, 70),
    )
    if game_state == "waiting":
        message = "Press Space to start"
    elif game_state == "paused":
        message = "Paused - Press Space to resume"
    elif game_state == "finished":
        winner = "Left player" if left_score > right_score else "Right player"
        message = f"{winner} wins! Press Space to play again"
    else:
        message = ""
    if message:
        draw_text(message, message_font, (width // 2, height // 2 - 40))
    if game_state in {"waiting", "finished"}:
        draw_text(
            f"Speed: {speed_options[speed_index]:g}x (Left/Right to change)",
            message_font, (width // 2, height // 2 + 40),
        )

    # Update the display
    pygame.display.flip()

    # Cap the frame rate
    tapped_keys.clear()
    clock.tick(60)