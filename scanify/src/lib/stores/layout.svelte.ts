// ---------------------------------------------------------------------------
// Layout store – Svelte 5 rune-based reactive state
// Persisted to localStorage
// ---------------------------------------------------------------------------

/** Position and size of a panel in the workspace grid. */
export interface PanelConfig {
  /** Unique panel identifier. */
  id: string;
  /** Human-readable panel title. */
  title: string;
  /** Panel component name / type key. */
  component: string;
  /** Grid column start (1-based). */
  col: number;
  /** Grid row start (1-based). */
  row: number;
  /** Number of grid columns the panel spans. */
  colSpan: number;
  /** Number of grid rows the panel spans. */
  rowSpan: number;
  /** Width in pixels (for absolute layouts). */
  width: number;
  /** Height in pixels (for absolute layouts). */
  height: number;
  /** Whether the panel is currently visible. */
  visible: boolean;
  /** Whether the panel is minimized / collapsed. */
  minimized: boolean;
  /** Panel z-index for stacking order. */
  zIndex: number;
  /** Arbitrary panel-specific settings. */
  settings: Record<string, unknown>;
}

/** A named layout preset that can be saved and restored. */
export interface LayoutPreset {
  id: string;
  name: string;
  description: string;
  panels: PanelConfig[];
  /** Whether this is a built-in preset (not deletable). */
  isBuiltIn: boolean;
  createdAt: string;
  updatedAt: string;
}

const STORAGE_KEY = 'scanify:layout';
const PRESETS_KEY = 'scanify:layout:presets';

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

function defaultPanels(): Map<string, PanelConfig> {
  const defaults: PanelConfig[] = [
    {
      id: 'scanner',
      title: 'Scanner',
      component: 'ScannerPanel',
      col: 1,
      row: 1,
      colSpan: 6,
      rowSpan: 4,
      width: 800,
      height: 500,
      visible: true,
      minimized: false,
      zIndex: 1,
      settings: {},
    },
    {
      id: 'chart',
      title: 'Chart',
      component: 'ChartPanel',
      col: 7,
      row: 1,
      colSpan: 6,
      rowSpan: 4,
      width: 800,
      height: 500,
      visible: true,
      minimized: false,
      zIndex: 1,
      settings: {},
    },
    {
      id: 'flow',
      title: 'Options Flow',
      component: 'FlowPanel',
      col: 1,
      row: 5,
      colSpan: 4,
      rowSpan: 3,
      width: 500,
      height: 350,
      visible: true,
      minimized: false,
      zIndex: 1,
      settings: {},
    },
    {
      id: 'alerts',
      title: 'Alerts',
      component: 'AlertsPanel',
      col: 5,
      row: 5,
      colSpan: 4,
      rowSpan: 3,
      width: 500,
      height: 350,
      visible: true,
      minimized: false,
      zIndex: 1,
      settings: {},
    },
    {
      id: 'market',
      title: 'Market Internals',
      component: 'MarketPanel',
      col: 9,
      row: 5,
      colSpan: 4,
      rowSpan: 3,
      width: 500,
      height: 350,
      visible: true,
      minimized: false,
      zIndex: 1,
      settings: {},
    },
  ];

  return new Map(defaults.map((p) => [p.id, p]));
}

// ---------------------------------------------------------------------------
// Store factory
// ---------------------------------------------------------------------------

function createLayoutStore() {
  // ---- reactive state ----
  let panels = $state<Map<string, PanelConfig>>(defaultPanels());
  let activePresetId = $state<string | null>(null);
  let isLocked = $state(false);
  let gridColumns = $state(12);
  let gridRows = $state(8);
  let presets = $state<LayoutPreset[]>([]);
  let focusedPanelId = $state<string | null>(null);
  let nextZIndex = $state(10);

  // ---- derived ----

  let panelList = $derived([...panels.values()]);
  let visiblePanels = $derived(panelList.filter((p) => p.visible));
  let hiddenPanels = $derived(panelList.filter((p) => !p.visible));
  let panelCount = $derived(panels.size);
  let visibleCount = $derived(visiblePanels.length);
  let activePreset = $derived(
    activePresetId ? presets.find((p) => p.id === activePresetId) ?? null : null
  );

  // ---- persistence helpers ----

  function persistLayout(): void {
    try {
      const serialized = JSON.stringify({
        panels: [...panels.entries()],
        activePresetId,
        isLocked,
        gridColumns,
        gridRows,
      });
      localStorage.setItem(STORAGE_KEY, serialized);
    } catch {
      // Storage quota or access error – silently ignore
    }
  }

  function persistPresets(): void {
    try {
      localStorage.setItem(PRESETS_KEY, JSON.stringify(presets));
    } catch {
      // Silently ignore
    }
  }

  function loadFromStorage(): void {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const data = JSON.parse(raw) as {
          panels: [string, PanelConfig][];
          activePresetId: string | null;
          isLocked: boolean;
          gridColumns: number;
          gridRows: number;
        };
        panels = new Map(data.panels);
        activePresetId = data.activePresetId;
        isLocked = data.isLocked;
        gridColumns = data.gridColumns ?? 12;
        gridRows = data.gridRows ?? 8;
      }
    } catch {
      // Corrupt data – keep defaults
    }

    try {
      const rawPresets = localStorage.getItem(PRESETS_KEY);
      if (rawPresets) {
        presets = JSON.parse(rawPresets) as LayoutPreset[];
      }
    } catch {
      presets = [];
    }
  }

  // ---- actions ----

  /** Resize a panel by id. */
  function resizePanel(
    panelId: string,
    dimensions: Partial<Pick<PanelConfig, 'width' | 'height' | 'colSpan' | 'rowSpan'>>
  ): void {
    if (isLocked) return;
    const panel = panels.get(panelId);
    if (!panel) return;
    panels.set(panelId, { ...panel, ...dimensions });
    panels = new Map(panels);
    persistLayout();
  }

  /** Move a panel to a new grid position. */
  function movePanel(
    panelId: string,
    position: Partial<Pick<PanelConfig, 'col' | 'row'>>
  ): void {
    if (isLocked) return;
    const panel = panels.get(panelId);
    if (!panel) return;
    panels.set(panelId, { ...panel, ...position });
    panels = new Map(panels);
    persistLayout();
  }

  /** Toggle panel visibility. */
  function togglePanel(panelId: string): void {
    const panel = panels.get(panelId);
    if (!panel) return;
    panels.set(panelId, { ...panel, visible: !panel.visible });
    panels = new Map(panels);
    persistLayout();
  }

  /** Show a specific panel. */
  function showPanel(panelId: string): void {
    const panel = panels.get(panelId);
    if (!panel) return;
    panels.set(panelId, { ...panel, visible: true });
    panels = new Map(panels);
    persistLayout();
  }

  /** Hide a specific panel. */
  function hidePanel(panelId: string): void {
    const panel = panels.get(panelId);
    if (!panel) return;
    panels.set(panelId, { ...panel, visible: false });
    panels = new Map(panels);
    persistLayout();
  }

  /** Minimize / collapse a panel. */
  function toggleMinimize(panelId: string): void {
    const panel = panels.get(panelId);
    if (!panel) return;
    panels.set(panelId, { ...panel, minimized: !panel.minimized });
    panels = new Map(panels);
    persistLayout();
  }

  /** Bring a panel to the front of the stacking order. */
  function focusPanel(panelId: string): void {
    const panel = panels.get(panelId);
    if (!panel) return;
    focusedPanelId = panelId;
    panels.set(panelId, { ...panel, zIndex: nextZIndex });
    nextZIndex++;
    panels = new Map(panels);
  }

  /** Update arbitrary panel settings. */
  function updatePanelSettings(panelId: string, settings: Record<string, unknown>): void {
    const panel = panels.get(panelId);
    if (!panel) return;
    panels.set(panelId, {
      ...panel,
      settings: { ...panel.settings, ...settings },
    });
    panels = new Map(panels);
    persistLayout();
  }

  /** Add a new panel to the layout. */
  function addPanel(config: PanelConfig): void {
    panels.set(config.id, config);
    panels = new Map(panels);
    persistLayout();
  }

  /** Remove a panel from the layout. */
  function removePanel(panelId: string): void {
    panels.delete(panelId);
    panels = new Map(panels);
    if (focusedPanelId === panelId) focusedPanelId = null;
    persistLayout();
  }

  /** Apply a layout preset. */
  function setPreset(presetId: string): void {
    const preset = presets.find((p) => p.id === presetId);
    if (!preset) return;
    panels = new Map(preset.panels.map((p) => [p.id, { ...p }]));
    activePresetId = presetId;
    persistLayout();
  }

  /** Save the current layout as a new preset. */
  function saveLayout(name: string, description: string = ''): string {
    const id = `preset_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const preset: LayoutPreset = {
      id,
      name,
      description,
      panels: [...panels.values()].map((p) => ({ ...p })),
      isBuiltIn: false,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    presets.push(preset);
    activePresetId = id;
    persistPresets();
    persistLayout();
    return id;
  }

  /** Overwrite an existing user preset with the current layout. */
  function updatePreset(presetId: string): boolean {
    const idx = presets.findIndex((p) => p.id === presetId && !p.isBuiltIn);
    if (idx < 0) return false;
    presets[idx] = {
      ...presets[idx],
      panels: [...panels.values()].map((p) => ({ ...p })),
      updatedAt: new Date().toISOString(),
    };
    persistPresets();
    return true;
  }

  /** Delete a user-created preset. */
  function deletePreset(presetId: string): boolean {
    const idx = presets.findIndex((p) => p.id === presetId && !p.isBuiltIn);
    if (idx < 0) return false;
    presets.splice(idx, 1);
    if (activePresetId === presetId) activePresetId = null;
    persistPresets();
    return true;
  }

  /** Load a full layout from a serialized snapshot. */
  function loadLayout(snapshot: { panels: [string, PanelConfig][]; activePresetId?: string }): void {
    panels = new Map(snapshot.panels);
    activePresetId = snapshot.activePresetId ?? null;
    persistLayout();
  }

  /** Lock / unlock the layout from editing. */
  function setLocked(locked: boolean): void {
    isLocked = locked;
    persistLayout();
  }

  /** Toggle the layout lock. */
  function toggleLock(): void {
    isLocked = !isLocked;
    persistLayout();
  }

  /** Reset to the default layout. */
  function resetLayout(): void {
    panels = defaultPanels();
    activePresetId = null;
    isLocked = false;
    focusedPanelId = null;
    nextZIndex = 10;
    persistLayout();
  }

  /** Initialize by loading persisted state. */
  function initialize(): void {
    loadFromStorage();
  }

  // ---- public API ----
  return {
    // reactive getters
    get panels() {
      return panels;
    },
    get panelList() {
      return panelList;
    },
    get visiblePanels() {
      return visiblePanels;
    },
    get hiddenPanels() {
      return hiddenPanels;
    },
    get panelCount() {
      return panelCount;
    },
    get visibleCount() {
      return visibleCount;
    },
    get activePresetId() {
      return activePresetId;
    },
    get activePreset() {
      return activePreset;
    },
    get isLocked() {
      return isLocked;
    },
    get gridColumns() {
      return gridColumns;
    },
    get gridRows() {
      return gridRows;
    },
    get presets() {
      return presets;
    },
    get focusedPanelId() {
      return focusedPanelId;
    },

    // actions
    resizePanel,
    movePanel,
    togglePanel,
    showPanel,
    hidePanel,
    toggleMinimize,
    focusPanel,
    updatePanelSettings,
    addPanel,
    removePanel,
    setPreset,
    saveLayout,
    updatePreset,
    deletePreset,
    loadLayout,
    setLocked,
    toggleLock,
    resetLayout,
    initialize,
  };
}

export const layoutStore = createLayoutStore();
