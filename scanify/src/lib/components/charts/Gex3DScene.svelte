<script lang="ts">
  // ---------------------------------------------------------------------------
  // Gex3DScene — the Three.js scene graph for the 3D Gamma Exposure profile.
  // Rendered inside a Threlte <Canvas>. Builds a row of paired call/put bars
  // per strike, mapped with d3 linear scales, lit for a high-end metallic look,
  // with a gently auto-orbiting camera (drag to explore).
  // ---------------------------------------------------------------------------
  import { T, useTask } from '@threlte/core';
  import { OrbitControls, Grid } from '@threlte/extras';
  import { scaleLinear } from 'd3';

  interface GexBar {
    strike: number;
    callGex: number;
    putGex: number;
    net: number;
  }

  let {
    profile = [],
    keyStrike = 0,
  }: { profile: GexBar[]; keyStrike?: number } = $props();

  // --- d3 scales -------------------------------------------------------------
  const maxAbs = $derived(
    Math.max(
      0.0001,
      ...profile.flatMap((d) => [Math.abs(d.callGex), Math.abs(d.putGex)]),
    ),
  );
  const heightScale = $derived(scaleLinear().domain([0, maxAbs]).range([0.04, 4.2]));

  const n = $derived(profile.length);
  const spacing = 1.15;
  const barW = 0.62;
  const xFor = (i: number) => (i - (n - 1) / 2) * spacing;

  // --- gentle auto-rotation (OrbitControls also handles drag) ----------------
  let spin = $state(0);
  useTask((delta) => {
    spin += delta * 0.18;
  });
</script>

<T.PerspectiveCamera makeDefault position={[0, 6.5, 15]} fov={38}>
  <OrbitControls
    enableDamping
    dampingFactor={0.08}
    enablePan={false}
    minDistance={9}
    maxDistance={26}
    minPolarAngle={0.25}
    maxPolarAngle={1.45}
    target={[0, 1.6, 0]}
  />
</T.PerspectiveCamera>

<!-- Lighting: soft ambient fill + key directional + colored rim accents -->
<T.AmbientLight intensity={0.55} />
<T.DirectionalLight position={[9, 16, 9]} intensity={1.5} />
<T.PointLight position={[-8, 7, 7]} intensity={42} color="#7c5cff" distance={40} decay={1.4} />
<T.PointLight position={[9, 4, -7]} intensity={28} color="#1f9d6b" distance={40} decay={1.6} />

<T.Group rotation.y={spin}>
  {#each profile as d, i (d.strike)}
    {@const callH = heightScale(Math.abs(d.callGex))}
    {@const putH = heightScale(Math.abs(d.putGex))}
    {@const isKey = d.strike === keyStrike}

    <!-- Call gamma bar (green, back row) -->
    <T.Mesh position={[xFor(i), callH / 2, -0.7]}>
      <T.BoxGeometry args={[barW, callH, barW]} />
      <T.MeshStandardMaterial
        color={isKey ? '#34e29b' : '#10b981'}
        metalness={0.45}
        roughness={0.32}
        emissive="#0a5f43"
        emissiveIntensity={isKey ? 0.6 : 0.28}
      />
    </T.Mesh>

    <!-- Put gamma bar (red, front row) -->
    <T.Mesh position={[xFor(i), putH / 2, 0.7]}>
      <T.BoxGeometry args={[barW, putH, barW]} />
      <T.MeshStandardMaterial
        color={isKey ? '#ff6b6b' : '#ef4444'}
        metalness={0.45}
        roughness={0.32}
        emissive="#7f1d1d"
        emissiveIntensity={isKey ? 0.6 : 0.28}
      />
    </T.Mesh>

    <!-- Key-strike marker pillar -->
    {#if isKey}
      <T.Mesh position={[xFor(i), 0.02, 0]}>
        <T.CylinderGeometry args={[0.05, 0.05, 5.4, 12]} />
        <T.MeshStandardMaterial
          color="#c9b8ff"
          emissive="#7c5cff"
          emissiveIntensity={0.8}
          metalness={0.2}
          roughness={0.4}
        />
      </T.Mesh>
    {/if}
  {/each}

  <!-- Reference grid floor for depth -->
  <Grid
    position={[0, 0, 0]}
    cellSize={1.15}
    cellColor="#1c2536"
    sectionSize={5.75}
    sectionColor="#2d3a55"
    fadeDistance={34}
    fadeStrength={1.2}
    infiniteGrid
  />
</T.Group>
