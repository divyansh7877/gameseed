(async function bootstrap() {
  if (!window.Phaser) {
    document.getElementById("game-root").innerHTML = "<p>Phaser failed to load.</p>";
    return;
  }

  const response = await fetch(window.GAME_MANIFEST_URL);
  if (!response.ok) {
    document.getElementById("game-root").innerHTML = "<p>Manifest is not ready.</p>";
    return;
  }
  const manifest = await response.json();
  const meta = document.getElementById("meta");
  meta.innerHTML = `
    <p><strong>${manifest.ui.title}</strong></p>
    <p>${manifest.ui.subtitle}</p>
    <p>Difficulty: ${manifest.runner_spec.difficulty}</p>
    <p>Theme: ${manifest.runner_spec.theme}</p>
  `;

  let phaserGame = null;

  class BootScene extends Phaser.Scene {
    constructor() {
      super("boot");
    }

    preload() {
      this.load.image("player-main", manifest.player.url);
      Object.entries(manifest.player.frames || {}).forEach(([key, url]) => {
        this.load.image(`player-${key}`, url);
      });
      manifest.obstacles.forEach((asset) => this.load.image(asset.asset_id, asset.url));
      this.load.image(manifest.collectible.asset_id, manifest.collectible.url);
      manifest.backgrounds.forEach((layer) => this.load.image(layer.asset_id, layer.url));
    }

    create() {
      this.scene.start("menu");
    }
  }

  class MenuScene extends Phaser.Scene {
    constructor() {
      super("menu");
    }

    create() {
      const { width, height } = this.scale;
      this.add.text(width / 2, height * 0.26, manifest.ui.title, {
        fontFamily: "Trebuchet MS",
        fontSize: "46px",
        color: "#ffffff",
      }).setOrigin(0.5);
      this.add.text(width / 2, height * 0.36, manifest.prompt, {
        fontFamily: "Trebuchet MS",
        fontSize: "22px",
        align: "center",
        wordWrap: { width: width * 0.7 },
        color: "#d6efff",
      }).setOrigin(0.5);
      const prompt = this.add.text(width / 2, height * 0.64, "Click or press Space to start", {
        fontFamily: "Trebuchet MS",
        fontSize: "24px",
        color: "#ffe66d",
      }).setOrigin(0.5);
      this.tweens.add({ targets: prompt, alpha: 0.25, yoyo: true, repeat: -1, duration: 650 });
      this.input.once("pointerdown", () => this.scene.start("play"));
      this.input.keyboard.once("keydown-SPACE", () => this.scene.start("play"));
    }
  }

  class PlayScene extends Phaser.Scene {
    constructor() {
      super("play");
    }

    create() {
      const { width, height } = this.scale;
      this.elapsedMs = 0;
      this.score = 0;
      this.scheduleIndex = 0;
      this.ended = false;

      const skyTop = Phaser.Display.Color.HexStringToColor(manifest.sky_gradient[0]).color;
      const skyMid = Phaser.Display.Color.HexStringToColor(manifest.sky_gradient[1]).color;
      const skyLow = Phaser.Display.Color.HexStringToColor(manifest.sky_gradient[2]).color;
      this.add.rectangle(width / 2, height / 2, width, height, skyTop, 1);
      this.add.rectangle(width / 2, height * 0.26, width * 1.08, height * 0.62, skyMid, 0.24);
      this.add.rectangle(width / 2, height * 0.74, width * 1.12, height * 0.44, skyLow, 0.18);
      this.add.ellipse(width * 0.78, height * 0.18, 220, 220, skyLow, 0.12);

      this.backgrounds = manifest.backgrounds.map((layer) => {
        const layout = this.backgroundLayout(layer.layer, width, height);
        const sprite = this.add.tileSprite(layout.x, layout.y, layout.width, layout.height, layer.asset_id)
          .setAlpha(layer.alpha)
          .setDepth(layer.depth)
          .setTint(Phaser.Display.Color.HexStringToColor(layer.blend_tint).color);
        sprite.setBlendMode(layer.layer === "near" ? Phaser.BlendModes.NORMAL : Phaser.BlendModes.SCREEN);
        return { sprite, config: layer, layout };
      });

      this.add.rectangle(width / 2, height * 0.78, width * 1.1, height * 0.26, skyLow, 0.08).setDepth(3);
      this.add.rectangle(width / 2, height * 0.9, width, 110, 0x05070d, 0.32).setDepth(4);

      this.add.rectangle(width / 2, manifest.physics.ground_y + 68, width, 220, 0x111827, 0.9);
      this.add.rectangle(width / 2, manifest.physics.ground_y + 18, width, 6, 0xffffff, 0.08);

      this.physics.world.gravity.y = manifest.physics.gravity_y;
      this.player = this.physics.add.sprite(manifest.physics.player_start_x, manifest.physics.ground_y - 60, "player-main");
      this.player.setScale(0.7);
      this.player.setCollideWorldBounds(true);
      this.player.body.setSize(this.player.width * 0.55, this.player.height * 0.86);
      this.player.body.setOffset(this.player.width * 0.22, this.player.height * 0.08);

      this.ground = this.add.rectangle(width / 2, manifest.physics.ground_y + 90, width, 24, 0x000000, 0);
      this.physics.add.existing(this.ground, true);
      this.physics.add.collider(this.player, this.ground);

      this.obstacles = this.physics.add.group();
      this.collectibles = this.physics.add.group();
      this.physics.add.overlap(this.player, this.obstacles, () => this.finish(false), undefined, this);
      this.physics.add.overlap(this.player, this.collectibles, (_, collectible) => {
        collectible.destroy();
        this.score += 1;
        this.scoreText.setText(`Score ${this.score}`);
      });

      this.scoreText = this.add.text(36, 28, "Score 0", {
        fontFamily: "Trebuchet MS",
        fontSize: "28px",
        color: "#f8fafc",
      }).setDepth(20);
      this.timerText = this.add.text(width - 36, 28, `${manifest.session_length_sec}s`, {
        fontFamily: "Trebuchet MS",
        fontSize: "28px",
        color: "#f8fafc",
      }).setOrigin(1, 0).setDepth(20);

      this.cursors = this.input.keyboard.createCursorKeys();
      this.input.on("pointerdown", () => this.jump());
      this.input.keyboard.on("keydown-SPACE", () => this.jump());

      this.tweens.add({
        targets: this.player,
        scaleX: 0.72,
        scaleY: 0.68,
        duration: 260,
        yoyo: true,
        repeat: -1,
      });
    }

    backgroundLayout(layerName, width, height) {
      if (layerName === "far") {
        return { x: width / 2, y: height / 2, width, height };
      }
      if (layerName === "mid") {
        return { x: width / 2, y: height * 0.57, width, height: height * 0.82 };
      }
      return { x: width / 2, y: height * 0.72, width, height: height * 0.58 };
    }

    jump() {
      if (this.ended) return;
      if (this.player.body.blocked.down || this.player.body.touching.down) {
        this.player.setVelocityY(manifest.physics.jump_velocity);
      }
    }

    spawn(event) {
      if (event.kind === "collectible") {
        const pickup = this.collectibles.create(this.scale.width + 60, manifest.lane_positions[event.lane], manifest.collectible.asset_id);
        pickup.setScale(0.42);
        pickup.body.allowGravity = false;
        pickup.setVelocityX(-manifest.physics.scroll_speed);
        return;
      }

      const asset = manifest.obstacles.find((item) => item.asset_id === event.asset_id);
      const obstacle = this.obstacles.create(this.scale.width + 120, manifest.lane_positions[event.lane], event.asset_id);
      obstacle.setScale(0.58);
      obstacle.body.allowGravity = false;
      obstacle.setVelocityX(-manifest.physics.scroll_speed);
      const bodyWidth = Math.max(28, obstacle.width * (event.lane === "air" ? 0.48 : 0.62));
      const bodyHeight = Math.max(28, obstacle.height * 0.68);
      obstacle.body.setSize(bodyWidth, bodyHeight);
      obstacle.body.setOffset((obstacle.width - bodyWidth) / 2, (obstacle.height - bodyHeight) / 2);
      obstacle.assetMeta = asset;
    }

    update(_, delta) {
      if (this.ended) return;
      this.elapsedMs += delta;
      this.backgrounds.forEach(({ sprite, config }) => {
        sprite.tilePositionX += (manifest.physics.scroll_speed * config.speed_multiplier * delta) / 1000;
      });
      while (this.scheduleIndex < manifest.spawn_table.length && manifest.spawn_table[this.scheduleIndex].time_ms <= this.elapsedMs) {
        this.spawn(manifest.spawn_table[this.scheduleIndex]);
        this.scheduleIndex += 1;
      }
      this.obstacles.children.each((child) => {
        if (child.x < -140) child.destroy();
      });
      this.collectibles.children.each((child) => {
        if (child.x < -140) child.destroy();
      });
      const remaining = Math.max(0, Math.ceil((manifest.session_length_sec * 1000 - this.elapsedMs) / 1000));
      this.timerText.setText(`${remaining}s`);
      if (this.elapsedMs >= manifest.session_length_sec * 1000) {
        this.finish(true);
      }
    }

    finish(victory) {
      if (this.ended) return;
      this.ended = true;
      this.scene.start("gameover", { victory, score: this.score });
    }
  }

  class GameOverScene extends Phaser.Scene {
    constructor() {
      super("gameover");
    }

    create(data) {
      const { width, height } = this.scale;
      this.add.rectangle(width / 2, height / 2, width, height, 0x030712, 0.86);
      this.add.text(width / 2, height * 0.32, data.victory ? "Run Complete" : "Run Failed", {
        fontFamily: "Trebuchet MS",
        fontSize: "44px",
        color: data.victory ? "#8adfff" : "#ffd6a5",
      }).setOrigin(0.5);
      this.add.text(width / 2, height * 0.45, `Score ${data.score}`, {
        fontFamily: "Trebuchet MS",
        fontSize: "28px",
        color: "#f8fafc",
      }).setOrigin(0.5);
      this.add.text(width / 2, height * 0.6, "Press Space or tap to retry", {
        fontFamily: "Trebuchet MS",
        fontSize: "24px",
        color: "#ffe66d",
      }).setOrigin(0.5);
      this.input.once("pointerdown", () => this.scene.start("play"));
      this.input.keyboard.once("keydown-SPACE", () => this.scene.start("play"));
    }
  }

  function startGame() {
    if (phaserGame) {
      phaserGame.destroy(true);
    }
    phaserGame = new Phaser.Game({
      type: Phaser.AUTO,
      width: 1280,
      height: 720,
      parent: "game-root",
      physics: {
        default: "arcade",
        arcade: {
          gravity: { y: manifest.physics.gravity_y },
          debug: false,
        },
      },
      scene: [BootScene, MenuScene, PlayScene, GameOverScene],
      render: {
        antialias: true,
        pixelArt: false,
      },
    });
  }

  document.getElementById("restart").addEventListener("click", startGame);
  startGame();
})();
