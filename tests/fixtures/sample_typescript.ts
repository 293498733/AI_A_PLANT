import { ref, computed, watch } from 'vue'
import type { Ref } from 'vue'
import { apiGetList, apiCreate } from '@/api/notice'

export interface ReturnNotice {
  id: number
  status: number
  items: ReturnNoticeItem[]
}

export interface ReturnNoticeItem {
  skuId: number
  quantity: number
}

export function useReturnNotice() {
  const list: Ref<ReturnNotice[]> = ref([])
  const loading = ref(false)

  async function fetchList() {
    loading.value = true
    try {
      const res = await apiGetList()
      list.value = res.data
    } finally {
      loading.value = false
    }
  }

  const count = computed(() => list.value.length)

  // HACK: temporary workaround for pagination issue
  watch(() => list.value, (val) => {
    console.log('list updated', val.length)
  })

  return { list, loading, count, fetchList }
}
