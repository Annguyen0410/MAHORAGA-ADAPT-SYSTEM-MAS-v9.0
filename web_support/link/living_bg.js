// ==================== Living Background (Bio-Digital Shader) ====================
// A reactive WebGL background that breathes and changes with time/activity

const LivingBackground = {
    scene: null,
    camera: null,
    renderer: null,
    material: null,
    mesh: null,
    startTime: Date.now(),
    pulseIntensity: 0.0,
    targetPulse: 0.0,
    currentTheme: 'dark', // 'dark', 'light', 'chill'
    available: true,     // false when WebGL is unavailable → 2D fallback is painted
    _perf: {
        step: -1,                // degradation level: -1 = full quality
        ratioSteps: [1, 0.75, 0.5],
        interval: 33,            // ms between rendered frames (33 ≈ 30fps ambient cap)
        frames: 0,
        lastCheck: 0,
        lastFrame: 0,
        settleAt: 0,             // when to drop to the lazy ambient rate
        settled: false,          // true once the intro animation has settled
        frozen: false            // true = animation stopped, last frame stays
    },

    config: {
        speed: 0.15, // Much slower for ambient feel
    baseColor: new THREE.Vector3(0.05, 0.02, 0.02),   // Dark: dark background
    accentColor: new THREE.Vector3(0.15, 0.08, 0.04), // Dark: very subtle accent
    },

    init() {
        console.log('🧬 Initializing Living Background...');

        // Sync with ThemeManager if already set
        const currentTheme = document.documentElement.getAttribute('data-theme');
        if (currentTheme) {
            this.currentTheme = currentTheme;
        }

        const canvas = document.getElementById('livingBackgroundCanvas');
        if (!canvas) {
            console.error('Living Background canvas not found!');
            return;
        }

        // 1. Setup Three.js — WebGL can be unavailable (embedded QtWebEngine
        //    without ANGLE, VMs, blocked GPU). Degrade to a static 2D backdrop
        //    instead of leaving the page blank.
        try {
            this.scene = new THREE.Scene();
            this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

            this.renderer = new THREE.WebGLRenderer({
                canvas: canvas,
                alpha: true,
                antialias: false
            });
            this.renderer.setSize(window.innerWidth, window.innerHeight);
            this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.25));
        } catch (e) {
            console.warn('🧬 Living Background: WebGL unavailable — using static 2D fallback.', e);
            this.available = false;
            this._drawFallback();
            return;
        }
        this.available = true;
        this._perf.lastCheck = performance.now();
        this._perf.lastFrame = performance.now();
        this._perf.settleAt = performance.now() + 12000;  // drop to idle rate after the intro
        this._detectSoftwareGL();
        // Manual override: localStorage linkLumina_perf = 'low' → force low quality
        try {
            if (localStorage.getItem('linkLumina_perf') === 'low') this._degrade(1);
        } catch (e) { /* ignore */ }

        // 2. Create Shader Material
        const uniforms = {
            uTime: { value: 0 },
            uResolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
            uBaseColor: { value: this.config.baseColor },
            uAccentColor: { value: this.config.accentColor },
            uPulse: { value: 0.0 },
            uDayTime: { value: 0.0 },
            uVignette: { value: 0.5 } // Dark: 0.5 (dark corners), Light/Chill: 0.2
        };

        this.material = new THREE.ShaderMaterial({
            uniforms: uniforms,
            vertexShader: `
                varying vec2 vUv;
                void main() {
                    vUv = uv;
                    gl_Position = vec4(position, 1.0);
                }
            `,
            fragmentShader: `
                uniform float uTime;
                uniform vec2 uResolution;
                uniform vec3 uBaseColor;
                uniform vec3 uAccentColor;
                uniform float uPulse;
                uniform float uVignette;
                varying vec2 vUv;

                // Simple noise function
                float random (in vec2 st) {
                    return fract(sin(dot(st.xy, vec2(12.9898,78.233)))*43758.5453123);
                }

                // Noise
                float noise (in vec2 st) {
                    vec2 i = floor(st);
                    vec2 f = fract(st);
                    float a = random(i);
                    float b = random(i + vec2(1.0, 0.0));
                    float c = random(i + vec2(0.0, 1.0));
                    float d = random(i + vec2(1.0, 1.0));
                    vec2 u = f * f * (3.0 - 2.0 * f);
                    return mix(a, b, u.x) + (c - a)* u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
                }

                #define OCTAVES 6
                float fbm (in vec2 st) {
                    float value = 0.0;
                    float amplitude = .5;
                    float frequency = 0.;
                    for (int i = 0; i < OCTAVES; i++) {
                        value += amplitude * noise(st);
                        st *= 2.;
                        amplitude *= .5;
                    }
                    return value;
                }

                void main() {
                    vec2 st = gl_FragCoord.xy/uResolution.xy;
                    st.x *= uResolution.x/uResolution.y;
                    
                    // Scale down coordinates to make the blobs/mesh larger (Aurora effect)
                    st *= 0.4;

                    vec2 q = vec2(0.);
                    q.x = fbm( st + 0.05*uTime);
                    q.y = fbm( st + vec2(1.0));

                    vec2 r = vec2(0.);
                    r.x = fbm( st + 1.0*q + vec2(1.7,9.2)+ 0.05*uTime );
                    r.y = fbm( st + 1.0*q + vec2(8.3,2.8)+ 0.04*uTime);

                    float f = fbm(st+r);

                    // Mix colors based on noise pattern
                    vec3 color = mix(uBaseColor, uAccentColor, clamp((f*f)*4.0, 0.0, 1.0));

                    color += uPulse * 0.2 * vec3(1.0, 0.85, 0.6);
                    float dist = distance(vUv, vec2(0.5));
                    color *= smoothstep(0.9 - uVignette * 0.4, 0.15, dist);

                    gl_FragColor = vec4(color, 1.0);
                }
            `
        });

        const geometry = new THREE.PlaneGeometry(2, 2);
        this.mesh = new THREE.Mesh(geometry, this.material);
        this.scene.add(this.mesh);

        // Apply the theme right away — Dark is dark, Light/Chill follow their palette
        if (this.currentTheme === 'dark') {
            this.updateCircadianRhythm();
        } else {
            this.setTheme(this.currentTheme);
        }

        // 4. Start Loop
        this.animate();
        if (this._perf.frozen) {
            // Software WebGL: settle the palette, paint one ambient frame, stay idle.
            try {
                for (let i = 0; i < 60; i++) this.updateColors();
                this.renderer.render(this.scene, this.camera);
            } catch (e) { /* ignore */ }
        }

        // 5. Connect Events
        this.setupVitalSigns();

        // Handle Resize — debounced to avoid thrashing
        let resizeTicking = false;
        window.addEventListener('resize', () => {
            if (resizeTicking) return;
            resizeTicking = true;
            requestAnimationFrame(() => {
                this.onWindowResize();
                resizeTicking = false;
            });
        }, { passive: true });

        // Pause when tab hidden (Page Visibility API) — saves CPU/GPU
        document.addEventListener('visibilitychange', () => {
            this._visible = document.visibilityState === 'visible';
        });
        this._visible = !document.hidden;
    },

    animate() {
        // When frozen the loop stops scheduling frames entirely — zero idle wakeups.
        if (this._perf.frozen) return;
        requestAnimationFrame(() => this.animate());
        if (!this._visible) return; // Skip render when tab hidden

        // Frame-rate gate — skips frames on slow (software) WebGL so the UI stays responsive
        const now = performance.now();
        if (now - this._perf.lastFrame < this._perf.interval) return;
        this._perf.lastFrame = now;

        // After the intro, settle to a lazy ambient rate so the decorative
        // shader stops burning GPU forever on weak/software WebGL.
        if (!this._perf.settled && this._perf.settleAt && now >= this._perf.settleAt) {
            this._perf.settled = true;
            this._perf.interval = 80; // ~12.5fps ambient
        }

        // FPS monitor (only while at full rate): step quality down if we can't keep up
        this._perf.frames++;
        if (!this._perf.settled && now - this._perf.lastCheck > 2000) {
            const fps = (this._perf.frames * 1000) / (now - this._perf.lastCheck);
            this._perf.frames = 0;
            this._perf.lastCheck = now;
            if (fps < 20) {
                // Way too slow — freeze the last frame (background stays painted)
                this._perf.frozen = true;
                document.documentElement.classList.add('low-perf');
                console.warn('🧬 Living Background: FPS too low (' + Math.round(fps) + ') — freezing animation.');
                return;
            }
            if (fps < 30 && this._perf.step < this._perf.ratioSteps.length - 1) {
                this._degrade(this._perf.step + 1);
            }
        }

        const elapsed = (Date.now() - this.startTime) / 1000;

        // Update Time
        this.material.uniforms.uTime.value = elapsed * this.config.speed;

        // Smooth Pulse Decay
        this.pulseIntensity += (this.targetPulse - this.pulseIntensity) * 0.1;
        this.material.uniforms.uPulse.value = this.pulseIntensity;
        if (this.targetPulse > 0) this.targetPulse -= 0.05;
        if (this.targetPulse < 0) this.targetPulse = 0;

        // Update Colors logic
        if (this.currentTheme === 'dark') {
            this.updateCircadianRhythm(); // Only auto-update targets in dark mode
        }
        // Always smoothly lerp towards target colors
        this.updateColors();

        this.renderer.render(this.scene, this.camera);
    },

    // Theme palettes — Dark / Light / Chill (animation background follows the theme)
    themePalettes: {
        dark: null, // Dark uses updateCircadianRhythm (dark, easy on the eyes)
        light: {
    base: [0.98, 0.96, 0.94],    // Creamy light background (Light theme)
    accent: [0.75, 0.45, 0.15]   // Subtle red-gold accent
        },
        chill: {
    base: [0.2, 0.14, 0.1],      // Warm sepia background (Chill theme)
    accent: [0.5, 0.35, 0.15]    // Subtle crimson + gold
        }
    },

    targetBase: { r: 0.06, g: 0.02, b: 0.02 },
    targetAccent: { r: 0.2, g: 0.12, b: 0.06 },

    setTheme(themeName) {
        this.currentTheme = themeName;
        if (typeof console !== 'undefined' && console.log) console.log('🎨 LivingBackground: Theme set to', themeName);

        if (!this.material) {
            // No WebGL — repaint the static fallback with the new theme colors
            this._drawFallback();
            return;
        }

        this.material.uniforms.uVignette.value = themeName === 'dark' ? 0.45 : (themeName === 'chill' ? 0.3 : 0.18);

        if (themeName === 'dark') {
            this.updateCircadianRhythm();
            this._renderOnceIfFrozen();
            return;
        }
        const palette = this.themePalettes[themeName];
        if (palette) {
            this.targetBase = { r: palette.base[0], g: palette.base[1], b: palette.base[2] };
            this.targetAccent = { r: palette.accent[0], g: palette.accent[1], b: palette.accent[2] };
        }
        this._renderOnceIfFrozen();
    },

    // Dark mode: dark background, very subtle accent — easy on the eyes, no glare
    updateCircadianRhythm() {
        const hours = new Date().getHours();
        const minutes = new Date().getMinutes();
        const timeValue = hours + minutes / 60;

        let base, accent;

        if (timeValue >= 5 && timeValue < 8) {
            base = [0.12, 0.01, 0.01]; accent = [0.35, 0.02, 0.02];  // Dawn: deep red, some light
        } else if (timeValue >= 8 && timeValue < 12) {
            base = [0.15, 0.02, 0.02]; accent = [0.45, 0.05, 0.05];   // Morning: bright red
        } else if (timeValue >= 12 && timeValue < 17) {
            base = [0.15, 0.02, 0.02]; accent = [0.45, 0.05, 0.05];   // Afternoon: bright red
        } else if (timeValue >= 17 && timeValue < 20) {
            base = [0.18, 0.01, 0.01]; accent = [0.55, 0.03, 0.03];  // Sunset: very bright red
        } else if (timeValue >= 20 && timeValue < 23) {
            base = [0.12, 0.01, 0.01]; accent = [0.35, 0.02, 0.02];  // Evening
        } else {
            base = [0.08, 0.00, 0.00]; accent = [0.25, 0.01, 0.01];   // Night: dark red
        }

        this.targetBase = { r: base[0], g: base[1], b: base[2] };
        this.targetAccent = { r: accent[0], g: accent[1], b: accent[2] };
    },

    // Smoothly lerp current colors towards target colors.
    // NOTE: the uniforms hold THREE.Vector3 (x/y/z), while targets are plain
    // {r,g,b} objects — lerp must touch .x/.y/.z, never .r (which is undefined
    // on Vector3 and would poison every frame with NaN, freezing the background
    // on one color regardless of theme).
    updateColors() {
        if (!this.material) return;

        const base = this.material.uniforms.uBaseColor.value;
        const accent = this.material.uniforms.uAccentColor.value;

        // Lerp factor - higher = faster transition
        const alpha = 0.02;

        base.x += (this.targetBase.r - base.x) * alpha;
        base.y += (this.targetBase.g - base.y) * alpha;
        base.z += (this.targetBase.b - base.z) * alpha;

        accent.x += (this.targetAccent.r - accent.x) * alpha;
        accent.y += (this.targetAccent.g - accent.y) * alpha;
        accent.z += (this.targetAccent.b - accent.z) * alpha;
    },

    setTargetColors(br, bg, bb, ar, ag, ab) {
        // Legacy function for backward compatibility
        this.targetBase = { r: br, g: bg, b: bb };
        this.targetAccent = { r: ar, g: ag, b: ab };
    },

    setupVitalSigns() {
        if (!window.EventBus) return;

        // Pulse on activity
        const triggerPulse = () => {
            this.targetPulse = 1.0; // Spike pulse
        };

        window.EventBus.on(window.EVENTS.LINK_ADDED, triggerPulse);
        window.EventBus.on(window.EVENTS.DECISION_LOGGED, triggerPulse);
        window.EventBus.on(window.EVENTS.FOLDER_CREATED, triggerPulse);

        console.log('💓 Vital Signs Connected');
    },

    onWindowResize() {
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.material.uniforms.uResolution.value.set(window.innerWidth, window.innerHeight);
        this._renderOnceIfFrozen();
    },

    // Detect software/fallback WebGL (SwiftShader, llvmpipe, WebKit WebGL...)
    // — it renders the fullscreen shader on the CPU, which is very slow.
    _detectSoftwareGL() {
        try {
            const gl = this.renderer.getContext();
            const label = String(gl.getParameter(gl.RENDERER) || '') + ' ' + String(gl.getParameter(gl.VENDOR) || '');
            if (/swiftshader|llvmpipe|softpipe|software|webkit webgl|mesa/i.test(label)) {
                console.warn('🧬 Living Background: software WebGL detected — painting one frame, then idle. (' + label.trim() + ')');
                this._degrade(0);
                this._perf.frozen = true;
                this._perf.settled = true;
            }
        } catch (e) { /* ignore */ }
    },

    // Step down rendering quality: lower pixel ratio + cap the frame rate.
    _degrade(step) {
        this._perf.step = step;
        const ratio = this._perf.ratioSteps[step];
        try {
            this.renderer.setPixelRatio(ratio);
            this.renderer.setSize(window.innerWidth, window.innerHeight);
            this.material.uniforms.uResolution.value.set(window.innerWidth, window.innerHeight);
        } catch (e) { /* ignore */ }
        this._perf.interval = step >= 2 ? 50 : 33;
        document.documentElement.classList.add('low-perf');
    },

    // Re-paint the single frozen frame when theme/size changes while idle.
    _renderOnceIfFrozen() {
        if (this._perf.frozen && this.renderer && this.material) {
            try { this.renderer.render(this.scene, this.camera); } catch (e) { /* ignore */ }
        }
    },

    // Static 2D backdrop used when WebGL is unavailable. Cheap (painted once,
    // repainted on resize/theme change) — no animation loop, zero CPU.
    _drawFallback() {
        const canvas = document.getElementById('livingBackgroundCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const isLight = this.currentTheme === 'light';
        const isChill = this.currentTheme === 'chill';
        const base = isLight ? '#f6efe3' : (isChill ? '#1a1410' : '#0a0808');
        const glow = isLight ? 'rgba(185, 28, 28, 0.08)' : 'rgba(185, 28, 28, 0.22)';

        const paint = () => {
            const w = (canvas.width = window.innerWidth);
            const h = (canvas.height = window.innerHeight);
            ctx.fillStyle = base;
            ctx.fillRect(0, 0, w, h);
            // Soft crimson glow radiating from the upper-left
            const g = ctx.createRadialGradient(w * 0.25, h * 0.15, 0, w * 0.5, h * 0.5, Math.max(w, h) * 0.9);
            g.addColorStop(0, glow);
            g.addColorStop(1, 'rgba(0, 0, 0, 0)');
            ctx.fillStyle = g;
            ctx.fillRect(0, 0, w, h);
        };

        paint();
        window.addEventListener('resize', paint, { passive: true });
    }
};

// Initialize on load (if Three.js is ready) — single check, no long polling
document.addEventListener('DOMContentLoaded', () => {
    if (typeof THREE !== 'undefined') {
        LivingBackground.init();
    } else {
        // Three.js CDN failed to load — still paint the 2D fallback
        LivingBackground._drawFallback();
        window.addEventListener('load', () => { if (typeof THREE !== 'undefined') LivingBackground.init(); });
    }
});
