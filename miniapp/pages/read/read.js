const API = "https://122.51.236.219:8000"
const app = getApp()

Page({
  data: { messages: [], input: "", satisfaction: false, status: "select-mode" },

  onLoad(opts) {
    this.bookId = opts.id
    wx.request({
      url: API + "/api/reading/resume/" + opts.id,
      header: { Authorization: "Bearer " + app.globalData.token },
      success: r => {
        if (r.statusCode === 200) this.setData({ messages: r.data.last_messages || [], status: r.data.status })
      }
    })
  },

  selectMode(m) {
    wx.request({
      url: API + "/api/reading/mode", method: "POST",
      header: { Authorization: "Bearer " + app.globalData.token },
      data: { book_id: this.bookId, mode: m, language: "zh" },
      success: () => this.setData({ status: "assessment" })
    })
  },

  onInput(e) { this.setData({ input: e.detail.value }) },

  send() {
    const msg = this.data.input; if (!msg) return
    const msgs = [...this.data.messages, { role: "user", content: msg }]
    this.setData({ messages: msgs, input: "" })

    const url = this.data.status === "assessment"
      ? API + "/api/reading/assessment"
      : API + "/api/reading/chat"

    wx.request({
      url, method: "POST",
      header: { Authorization: "Bearer " + app.globalData.token },
      data: { book_id: this.bookId, message: msg },
      success: r => {
        const ai = r.data.ai_message || r.data
        this.setData({ messages: [...this.data.messages, { role: "assistant", content: ai }] })
        if (r.data.next_action === "enter_reading") this.setData({ status: "reading" })
        if (Math.random() < 0.05 && this.data.messages.length > 6) this.setData({ satisfaction: true })
      }
    })
  },

  rate(e) {
    const ok = e.currentTarget.dataset.ok === "1"
    wx.request({
      url: API + "/api/analytics/event", method: "POST",
      data: { event: "satisfaction", props: { ok } }
    })
    this.setData({ satisfaction: false })
  }
})
