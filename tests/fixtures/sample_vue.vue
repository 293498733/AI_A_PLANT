<template>
  <div class="container">
    <h1>{{ title }}</h1>
    <el-table :data="list">
      <el-table-column prop="id" label="ID" />
      <el-table-column prop="name" label="Name" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const title = ref('Return Notice')
const list = ref([])

onMounted(async () => {
  const res = await fetch('/api/list')
  list.value = await res.json()
})
</script>

<style scoped>
.container {
  padding: 20px;
}
</style>
