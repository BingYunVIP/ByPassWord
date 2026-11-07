import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest'
import { useAuth } from './auth'
import { useVault } from './vault'
import * as vaultApi from '../api/vault'
import { createVaultKeys } from '../crypto/vault-crypto'
vi.mock('../api/auth', () => ({ logout:vi.fn(async () => ({})) }))
vi.mock('../api/vault', () => ({ getVault:vi.fn(), getSettings:vi.fn(async () => ({})), createItem:vi.fn() }))
const auth = useAuth(), vault = useVault()
function seed() {
  auth.pending.value = { email:'synthetic@example.com', kdf:{salt:btoa('a'.repeat(16)), memoryKib:8192,time:1,parallel:1}, encKey:new Uint8Array(32).fill(3), pendingDek:new Uint8Array(32).fill(4) }
  auth.dek.value = new Uint8Array(32).fill(1); auth.status.value = 'unlocked'
  vault.items.value = [{ id:'synthetic-item',type:'website',title:'Synthetic',password:'synthetic-password' }]
  vault.openEditModal(vault.items.value[0]); vault.passwordChangeForm.current = 'synthetic-master'; vault.generatedPassword.value = 'synthetic-generated'
}
beforeEach(() => { auth.clearSession(); vi.clearAllMocks() })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
describe('sensitive state lifetime', () => {
  it('clears keys, editor values, generated passwords and open dialogs on lock', () => {
    seed(); const key = auth.dek.value, pending = auth.pending.value.pendingDek
    auth.lock()
    expect(Array.from(key)).toEqual(new Array(32).fill(0))
    expect(Array.from(pending)).toEqual(new Array(32).fill(0))
    expect(auth.pending.value.pendingDek).toBe(null)
    expect(vault.items.value).toEqual([]); expect(vault.editingForm.value.password).toBe('')
    expect(vault.generatedPassword.value).toBe(''); expect(vault.passwordChangeForm.current).toBe('')
    expect(vault.activeModal.value).toBe(null)
  })
  it('clears the same state on logout and session invalidation', async () => {
    seed(); await auth.logout()
    expect(auth.status.value).toBe('anonymous'); expect(vault.editingForm.value.password).toBe('')
    seed(); auth.clearSession(); expect(vault.items.value).toEqual([])
  })
  it('discards a vault response that arrives after a lock', async () => {
    seed(); let resolve
    vi.mocked(vaultApi.getVault).mockReturnValue(new Promise(r => { resolve=r }))
    const work = vault.loadVault(); auth.lock()
    resolve({rev:1,folders:[],items:[]}); await work
    expect(vault.vaultLoaded.value).toBe(false); expect(vault.items.value).toEqual([])
  })
  it('does not repopulate an editor/list when a write response arrives after lock', async () => {
    seed(); vault.editingForm.value.id = null
    let release, entered
    const called = new Promise(resolve => { entered=resolve })
    vi.mocked(vaultApi.createItem).mockImplementation(() => { entered(); return new Promise(resolve => { release=resolve }) })
    const save = vault.saveItem(); await called; auth.lock(); release({rev:2}); await save
    expect(vault.items.value).toEqual([]); expect(vault.editingForm.value.password).toBe('')
  })
  it('abandons a real password KDF started before a lock', async () => {
    const keys = await createVaultKeys('Synthetic-Master#2026', { kdfOverrides:{memoryKib:8192,time:1,parallel:1} })
    auth.pending.value = {kdf:keys.kdf,wrappedDek:keys.wrappedDek,dekNonce:keys.dekNonce}; auth.status.value='locked'
    const unlock = auth.unlock('Synthetic-Master#2026'); auth.lock()
    await expect(unlock).rejects.toThrow('操作已取消')
    expect(auth.dek.value).toBe(null); expect(auth.pending.value.encKey).toBe(null)
  })
  it('attempts immediate clipboard clearing on lock instead of cancelling its only cleanup', () => {
    vi.useFakeTimers()
    const writeText = vi.fn(async () => {})
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    vi.stubGlobal('document', { createElement: () => ({ style: {}, select() {} }), body: { appendChild() {}, removeChild() {} }, execCommand: () => true })
    seed(); vault.securityConfig.clipboardClearSeconds = 10
    vault.copyText('synthetic-copied-password')
    auth.lock()
    expect(writeText).toHaveBeenCalledWith('')
    expect(vault.editingForm.value.password).toBe('')
  })
})
