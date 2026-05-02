const API = "https://122.51.236.219:8000"
const app = getApp()

Page({
  data: { books: [], loggedIn: false },

  onLoad() {
    if (app.globalData.token) { this.setData({ loggedIn: true }); this.loadBooks() }
  },

  login() {
    app.wxLogin((err, d) => {
      if (!err) { this.setData({ loggedIn: true }); wx.showToast({ title: "登录成功" }); this.loadBooks() }
      else wx.showToast({ title: "登录失败", icon: "none" })
    })
  },

  loadBooks() {
    wx.request({
      url: API + "/api/books",
      header: { Authorization: "Bearer " + app.globalData.token },
      success: r => this.setData({ books: r.data.items || [] })
    })
  },

  upload() {
    if (!app.globalData.token) { wx.showToast({ title: "请先登录", icon: "none" }); return }
    wx.chooseMessageFile({ count: 1, type: "file", success: res => this.doUpload(res.tempFiles[0]) })
  },

  uploadFromChat() {
    if (!app.globalData.token) { wx.showToast({ title: "请先登录", icon: "none" }); return }
    wx.chooseMessageFile({ count: 1, type: "file", success: res => this.doUpload(res.tempFiles[0]) })
  },

  doUpload(file) {
    wx.showLoading({ title: "上传中…" })
    wx.uploadFile({
      url: API + "/api/books/upload",
      filePath: file.path,
      name: "file",
      header: { Authorization: "Bearer " + app.globalData.token },
      formData: { title: file.name.replace(/\.[^.]+$/, "") },
      success: () => { wx.hideLoading(); this.loadBooks() },
      fail: () => { wx.hideLoading(); wx.showToast({ title: "上传失败", icon: "none" }) }
    })
  },

  openBook(e) {
    wx.navigateTo({ url: "/pages/read/read?id=" + e.currentTarget.dataset.id })
  }
})
