const API = "https://122.51.236.219:8000"
const app = getApp()

Page({
  data: { entries: [], query: "" },

  onLoad() { this.search() },

  onSearch(e) { this.setData({ query: e.detail.value }); this.search(e.detail.value) },

  search(q) {
    wx.request({
      url: API + "/api/wiki",
      header: { Authorization: "Bearer " + app.globalData.token },
      data: q ? { search: q } : {},
      success: r => this.setData({ entries: r.data || [] })
    })
  }
})
