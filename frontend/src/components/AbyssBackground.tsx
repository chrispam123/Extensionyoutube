// src/components/AbyssBackground.tsx
// Motor GPU: Raw WebGL sin librerías — humo etéreo con destellos blood (#8b0000)

import { useEffect, useRef, useState } from "react";
import "./AbyssBackground.css";

// ============================================================================
// SHADER GLSL — inline para máxima cohesión mientras experimentamos
// ============================================================================

const VERTEX_SHADER = /* glsl */ `
  attribute vec2 a_position;
  varying vec2 v_uv;
  void main() {
    v_uv = a_position * 0.5 + 0.5;
    gl_Position = vec4(a_position, 0.0, 1.0);
  }
`;

const FRAGMENT_SHADER = /* glsl */ `
  precision highp float;
  varying vec2 v_uv;
  uniform float u_time;
  uniform float u_intensity;   // 0.0 — 1.0: oscuridad del abismo
  uniform float u_blood_factor; // 0.0 — 1.0: presencia del #8b0000
  uniform vec2  u_resolution;

  // --- Funciones de ruido (simplex-like) ---
  float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
      mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x),
      f.y
    );
  }

  // fBM (Fractal Brownian Motion) — capas de ruido superpuestas
  float fbm(vec2 p) {
    float value = 0.0;
    float amp   = 0.5;
    float freq  = 1.0;
    for (int i = 0; i < 4; i++) {
      value += amp * noise(p * freq);
      freq  *= 2.0;
      amp   *= 0.5;
    }
    return value;
  }

  void main() {
    // Coordenadas normalizadas con distorsión por tiempo
    vec2 uv = v_uv;
    uv.x += sin(uv.y * 3.0 + u_time * 0.2) * 0.02;
    uv.y += cos(uv.x * 2.5 + u_time * 0.15) * 0.02;

    // Escala base + desplazamiento lento (el "humo")
    // Capas individuales de ruido
    float n1 = fbm(uv * 2.5 + u_time * 0.08);
    float n2 = fbm(uv * 4.0 - u_time * 0.05 + 1.0);
    float n3 = fbm(uv * 6.0 + u_time * 0.03 + 2.0);

    // --- MAPEO ESPECTRAL: 3 colores por banda de frecuencia ---
    // Baja frecuencia (n1): azul profundo — ondulaciones lentas
    vec3 blueDeep = vec3(0.02, 0.05, 0.18);
    float blueZone = smoothstep(0.2, 0.5, n1) * 0.4;

    // Media frecuencia (n2): rojo sangre — textura principal
    vec3 blood = vec3(0.545, 0.0, 0.0);
    float bloodZone = smoothstep(0.4, 0.7, n2) * u_blood_factor;

    // Alta frecuencia (n3): blanco — destellos finos
    vec3 whiteSpark = vec3(0.6, 0.55, 0.5);
    float whiteZone = smoothstep(0.55, 0.8, n3) * 0.3;

    // Mezcla: base oscura + bandas de color
    vec3 color = vec3(0.02); // negro base
    color = mix(color, blueDeep, blueZone);
    color = mix(color, blood, bloodZone * 0.6);
    color = mix(color, whiteSpark, whiteZone);

    gl_FragColor = vec4(color, 1.0);
  }
`;

// ============================================================================
// COMPONENTE
// ============================================================================

export default function AbyssBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const startTime = useRef<number>(0);
  const [webglFailed, setWebglFailed] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Resolución reducida al 50% → difuminado natural + ahorro GPU
    const dpr = Math.max(1, Math.floor(window.devicePixelRatio / 2));
    const width = canvas.clientWidth * dpr;
    const height = canvas.clientHeight * dpr;
    canvas.width = width;
    canvas.height = height;

    // --- Inicialización WebGL1 (máxima compatibilidad) ---
    const gl = canvas.getContext("webgl", { alpha: false, antialias: false });
    if (!gl) {
      console.warn("AbyssBackground: WebGL no disponible, usando fallback.");
      setWebglFailed(true);
      return;
    }

    // --- Compilar shader ---
    function compileShader(type: number, source: string): WebGLShader | null {
      const shader = gl!.createShader(type);
      if (!shader) return null;
      gl!.shaderSource(shader, source);
      gl!.compileShader(shader);
      if (!gl!.getShaderParameter(shader, gl!.COMPILE_STATUS)) {
        console.error("Shader error:", gl!.getShaderInfoLog(shader));
        gl!.deleteShader(shader);
        return null;
      }
      return shader;
    }

    const vs = compileShader(gl.VERTEX_SHADER, VERTEX_SHADER);
    const fs = compileShader(gl.FRAGMENT_SHADER, FRAGMENT_SHADER);
    if (!vs || !fs) return;

    const program = gl.createProgram();
    if (!program) return;
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error("Link error:", gl.getProgramInfoLog(program));
      return;
    }
    gl.useProgram(program);

    // --- Buffer del viewport (triángulo fullscreen) ---
    const positions = new Float32Array([
      -1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1,
    ]);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);

    const aPos = gl.getAttribLocation(program, "a_position");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    // --- Uniforms ---
    const uTime = gl.getUniformLocation(program, "u_time");
    const uIntensity = gl.getUniformLocation(program, "u_intensity");
    const uBlood = gl.getUniformLocation(program, "u_blood_factor");
    const uResolution = gl.getUniformLocation(program, "u_resolution");

    // Valores por defecto (ajustables desde el inspector si se exponen)
    startTime.current = performance.now();
    let running = true;

    // --- Bucle de animación con pausa por visibilidad ---
    function render(timestamp: number) {
      if (!running) return;

      if (!document.hidden) {
        const elapsed = (timestamp - startTime.current) / 1000.0;

        gl!.uniform1f(uTime, elapsed);
        gl!.uniform1f(uIntensity, 0.65);
        gl!.uniform1f(uBlood, 0.7);
        gl!.uniform2f(uResolution, width, height);

        gl!.drawArrays(gl!.TRIANGLES, 0, 6);
      }
      animRef.current = requestAnimationFrame(render);
    }

    // Listener: detener bucle cuando el panel pierde visibilidad
    const handleVisibility = () => {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(animRef.current);
      } else {
        running = true;
        animRef.current = requestAnimationFrame(render);
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);

    animRef.current = requestAnimationFrame(render);

    // --- Limpieza ---
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      running = false;
      cancelAnimationFrame(animRef.current);
      gl.deleteProgram(program);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
      gl.deleteBuffer(buffer);
    };
  }, []);

  // Si WebGL falló, no renderizar canvas → el gradiente CSS del body se ve
  if (webglFailed) return null;

  return <canvas ref={canvasRef} className="abyss-canvas" />;
}
