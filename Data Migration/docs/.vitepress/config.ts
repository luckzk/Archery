import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'PostgreSQL 迁移开发文档',
  description: '基于原生逻辑复制的 PostgreSQL 迁移控制台设计文档',
  lang: 'zh-CN',
  themeConfig: {
    nav: [
      { text: '方案总览', link: '/' },
      { text: 'MVP', link: '/mvp/' },
      { text: '后端接口', link: '/backend-api/' },
      { text: '前端控制台', link: '/frontend/' },
      { text: '序列设置', link: '/sequence/' },
      { text: '数据检查', link: '/data-check/' }
    ],
    sidebar: [
      {
        text: '迁移方案',
        items: [
          { text: '方案总览', link: '/' },
          { text: 'MVP 范围', link: '/mvp/' },
          { text: '技术栈', link: '/tech-stack/' },
          { text: '前端控制台', link: '/frontend/' },
          { text: '后续路线', link: '/roadmap/' }
        ]
      },
      {
        text: '核心能力',
        items: [
          { text: '实例管理', link: '/instances/' },
          { text: 'Replica Identity', link: '/replica-identity/' },
          { text: '一键设置序列', link: '/sequence/' },
          { text: '数据检查', link: '/data-check/' },
          { text: '数据库对象检查', link: '/object-check/' },
          { text: 'SQL 编辑器分析', link: '/sql-editor-archery-analysis/' }
        ]
      },
      {
        text: '后端接口',
        items: [
          { text: '接口总览', link: '/backend-api/' },
          { text: '启动与通用字段', link: '/backend-api/overview/' },
          { text: '实例接口', link: '/backend-api/instances/' },
          { text: '任务接口', link: '/backend-api/tasks/' },
          { text: '元数据接口', link: '/backend-api/metadata/' },
          { text: '序列接口', link: '/backend-api/sequences/' },
          { text: '数据检查接口', link: '/backend-api/data-check/' }
        ]
      }
    ],
    search: {
      provider: 'local'
    }
  }
})
