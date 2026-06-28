<script lang="ts">
  // ---------------------------------------------------------------------------
  // Gex3DChart — high-end 3D Gamma Exposure profile.
  // A Threlte <Canvas> hosting a Three.js bar field (call vs put gamma per
  // strike), with d3-scaled geometry, metallic materials and an auto-orbiting
  // camera. Client-only (the app runs with ssr=false), so WebGL is safe.
  // ---------------------------------------------------------------------------
  import { Canvas } from '@threlte/core';
  import Gex3DScene from './Gex3DScene.svelte';

  interface GexBar {
    strike: number;
    callGex: number;
    putGex: number;
    net: number;
  }

  let {
    profile = [],
    keyStrike = 0,
    height = '260px',
  }: { profile: GexBar[]; keyStrike?: number; height?: string } = $props();
</script>

<div class="gex3d" style="height:{height};">
  <Canvas>
    <Gex3DScene {profile} {keyStrike} />
  </Canvas>

  <div class="gex3d-legend">
    <span class="lg lg-call"><i></i>Call γ</span>
    <span class="lg lg-put"><i></i>Put γ</span>
    <span class="lg-hint">drag to rotate · scroll to zoom</span>
  </div>
</div>

<style>
  .gex3d {
    position: relative;
    width: 100%;
    border-radius: var(--radius-lg, 10px);
    overflow: hidden;
    background:
      radial-gradient(120% 90% at 50% 0%, oklch(0.18 0.03 275 / 0.55), transparent 70%),
      oklch(0.10 0.02 260 / 0.6);
    border: 1px solid var(--border-subtle, oklch(0.30 0.02 260 / 0.5));
  }

  .gex3d-legend {
    position: absolute;
    left: 10px;
    bottom: 8px;
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: var(--text-secondary, oklch(0.72 0.01 260));
    pointer-events: none;
  }

  .lg {
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }

  .lg i {
    width: 9px;
    height: 9px;
    border-radius: 2px;
    display: inline-block;
  }

  .lg-call i {
    background: #10b981;
    box-shadow: 0 0 8px #10b98199;
  }

  .lg-put i {
    background: #ef4444;
    box-shadow: 0 0 8px #ef444499;
  }

  .lg-hint {
    color: var(--text-tertiary, oklch(0.52 0.01 260));
    font-weight: 500;
    margin-left: auto;
  }
</style>
