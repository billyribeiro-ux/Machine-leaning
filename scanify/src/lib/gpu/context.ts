// ---------------------------------------------------------------------------
// WebGPU context manager for the Scanify trading scanner
// ---------------------------------------------------------------------------

/**
 * Manages the lifecycle of a WebGPU adapter and device.
 *
 * Uses lazy initialisation: the device is only created when {@link init} is
 * called, and can be torn down with {@link destroy}.
 */
export class GPUContext {
  private device: GPUDevice | null = null;
  private adapter: GPUAdapter | null = null;
  private initialized = false;

  // -----------------------------------------------------------------------
  // Lifecycle
  // -----------------------------------------------------------------------

  /**
   * Initialise the WebGPU adapter and device.
   *
   * @returns `true` when the device was successfully created, `false`
   *          otherwise (e.g. the browser does not support WebGPU).
   */
  async init(): Promise<boolean> {
    if (this.initialized && this.device !== null) {
      return true;
    }

    if (typeof navigator === 'undefined' || !('gpu' in navigator)) {
      console.warn('[GPUContext] WebGPU is not supported in this browser.');
      return false;
    }

    try {
      const gpu: GPU = navigator.gpu as GPU;
      this.adapter = await gpu.requestAdapter({
        powerPreference: 'high-performance',
      });

      if (!this.adapter) {
        console.warn('[GPUContext] Failed to obtain a GPU adapter.');
        return false;
      }

      this.device = await this.adapter.requestDevice({
        requiredFeatures: [],
        requiredLimits: {},
      });

      // Listen for device-lost events so downstream code can react.
      this.device.lost.then((info: GPUDeviceLostInfo) => {
        console.error(
          `[GPUContext] Device lost (reason: ${info.reason}): ${info.message}`,
        );
        this.device = null;
        this.initialized = false;
      });

      this.initialized = true;
      return true;
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : String(err);
      console.error(`[GPUContext] Initialisation failed: ${message}`);
      return false;
    }
  }

  // -----------------------------------------------------------------------
  // Accessors
  // -----------------------------------------------------------------------

  /** Return the active GPU device, or `null` if not initialised. */
  getDevice(): GPUDevice | null {
    return this.device;
  }

  /** Return the active GPU adapter, or `null` if not initialised. */
  getAdapter(): GPUAdapter | null {
    return this.adapter;
  }

  /** Whether the context has been successfully initialised. */
  isReady(): boolean {
    return this.initialized && this.device !== null;
  }

  // -----------------------------------------------------------------------
  // Resource helpers
  // -----------------------------------------------------------------------

  /**
   * Create a GPU buffer.
   *
   * @throws When the device is not initialised.
   */
  createBuffer(descriptor: GPUBufferDescriptor): GPUBuffer {
    const device = this.requireDevice();
    return device.createBuffer(descriptor);
  }

  /**
   * Create a render pipeline.
   *
   * @throws When the device is not initialised.
   */
  createRenderPipeline(
    descriptor: GPURenderPipelineDescriptor,
  ): GPURenderPipeline {
    const device = this.requireDevice();
    return device.createRenderPipeline(descriptor);
  }

  /**
   * Create a compute pipeline.
   *
   * @throws When the device is not initialised.
   */
  createComputePipeline(
    descriptor: GPUComputePipelineDescriptor,
  ): GPUComputePipeline {
    const device = this.requireDevice();
    return device.createComputePipeline(descriptor);
  }

  /**
   * Create a shader module from WGSL source.
   *
   * @throws When the device is not initialised.
   */
  createShaderModule(code: string, label?: string): GPUShaderModule {
    const device = this.requireDevice();
    return device.createShaderModule({ code, label });
  }

  /**
   * Create a bind group layout.
   *
   * @throws When the device is not initialised.
   */
  createBindGroupLayout(
    descriptor: GPUBindGroupLayoutDescriptor,
  ): GPUBindGroupLayout {
    const device = this.requireDevice();
    return device.createBindGroupLayout(descriptor);
  }

  /**
   * Create a bind group.
   *
   * @throws When the device is not initialised.
   */
  createBindGroup(descriptor: GPUBindGroupDescriptor): GPUBindGroup {
    const device = this.requireDevice();
    return device.createBindGroup(descriptor);
  }

  /**
   * Submit encoded command buffers to the device queue.
   */
  submit(commandBuffers: GPUCommandBuffer[]): void {
    const device = this.requireDevice();
    device.queue.submit(commandBuffers);
  }

  /**
   * Write data to a GPU buffer through the device queue.
   */
  writeBuffer(buffer: GPUBuffer, offset: number, data: BufferSource): void {
    const device = this.requireDevice();
    device.queue.writeBuffer(buffer, offset, data);
  }

  // -----------------------------------------------------------------------
  // Cleanup
  // -----------------------------------------------------------------------

  /** Destroy the device and release all GPU resources. */
  destroy(): void {
    if (this.device) {
      this.device.destroy();
      this.device = null;
    }
    this.adapter = null;
    this.initialized = false;
  }

  // -----------------------------------------------------------------------
  // Internal
  // -----------------------------------------------------------------------

  /**
   * Assert that the device is available and return it.
   *
   * @throws {Error} When the device has not been initialised.
   */
  private requireDevice(): GPUDevice {
    if (!this.device) {
      throw new Error(
        '[GPUContext] Device not initialised. Call init() first.',
      );
    }
    return this.device;
  }
}
